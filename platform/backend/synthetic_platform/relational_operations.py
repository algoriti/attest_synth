"""Post-generation aggregation and checks on declared parent-child links."""
import pandas as pd
from .spec import ColumnType


def relation(spec,operation):
    return next((r for r in spec.relationships if r.parent_table==operation.parent_table
        and r.child_table==operation.child_table and r.child_key==operation.child_key),None)


def aggregate(spec,frames):
    trace=[]
    for op in spec.aggregates:
        rel=relation(spec,op)
        parent,child=frames[op.parent_table],frames[op.child_table]
        grouped=child.groupby(op.child_key,dropna=True)
        if op.operation=='count': values=grouped.size()
        else:
            series=grouped[op.source_column]
            values=series.sum(min_count=1) if op.operation=='sum' else getattr(series,op.operation)()
        output=parent[rel.parent_key].map(values)
        if op.operation=='count': output=output.fillna(0).astype('int64')
        elif op.empty_value is not None: output=output.fillna(op.empty_value)
        parent[op.target_column]=output
        trace.append(dict(table=op.parent_table,column=op.target_column,operation=op.operation,
            source=op.child_table,group_key=op.child_key,empty_value=op.empty_value,
            denominator='all linked child rows' if op.operation=='count' else 'non-null source values for each parent',
            excluded_null_links=int(child[op.child_key].isna().sum())))
    return trace


def _required_empty(table, column_name, frame):
    """Rows where a declared implies_null rule requires `column_name` to be empty."""
    from .evaluate import null_rule_condition
    from .spec import ConstraintOperator
    mask = pd.Series(False, index=frame.index)
    for constraint in table.constraints:
        if (constraint.operator == ConstraintOperator.IMPLIES_NULL and len(constraint.columns) == 2
                and constraint.columns[1] == column_name and constraint.columns[0] in frame):
            mask |= null_rule_condition(frame, constraint)
    return mask


def check_cross_table(spec,frames):
    checks=[]
    for op in spec.cross_table_constraints:
        rel=relation(spec,op)
        parent,child=frames[op.parent_table],frames[op.child_table]
        bound=child[op.child_key].map(parent.set_index(rel.parent_key)[op.parent_column])
        value=child[op.child_column]
        col=spec.table(op.child_table).column(op.child_column)
        if col.type in (ColumnType.DATE,ColumnType.TIMESTAMP):
            bound=pd.to_datetime(bound,format='mixed',utc=True,errors='coerce')
            value=pd.to_datetime(value,format='mixed',utc=True,errors='coerce')
        missing=bound.isna()|value.isna()
        # A value the specification itself requires to be empty ("no score for a missing
        # submission") cannot also fail this rule; it is counted as skipped, not failed.
        required_empty=_required_empty(spec.table(op.child_table), op.child_column, child)
        bad=(value>bound) if op.operator=='less_or_equal' else (value<bound)
        if op.missing=='fail': bad |= missing & ~required_empty
        skipped=int(missing.sum()) if op.missing=='skip' else int((missing & required_empty).sum())
        checks.append(dict(relationship=f'{op.child_table}.{op.child_column} {op.operator} {op.parent_table}.{op.parent_column}',
            passed=not bad.any(),failing_rows=int(bad.sum()),skipped_rows=skipped))
    return checks


def enforce_cross_table(spec, frames, table_name, rng):
    """Make generated child values respect their declared parent bounds.

    A cross-table rule always has the same shape whatever the domain: a child value
    bounded by a value on its parent row — a score under its assessment's maximum, a
    delivery after its order, a payment under its invoice. The rule engine samples
    each column on its own, so without this step those rules were only *checked*
    afterwards: a student performance run produced 3,642 scores above their maximum.

    Violating rows are redrawn uniformly inside the allowed range rather than clipped
    to the bound, so values do not pile up exactly at the limit. Only generated
    columns (rule or learned) are changed; derived, key and aggregate columns are
    left for the final checks to report. Every changed row is counted and returned,
    and rows whose allowed range is empty are left alone and counted as unsatisfiable.
    """
    import numpy as np
    from .spec import SemanticRole

    table = spec.table(table_name)
    trace = []
    for op in spec.cross_table_constraints:
        if op.child_table != table_name:
            continue
        column = table.column(op.child_column)
        parent_table = spec.table(op.parent_table)
        parent_column = parent_table.column(op.parent_column) if parent_table else None
        rel = relation(spec, op)
        if (column is None or parent_column is None or rel is None
                or column.role not in (SemanticRole.RULE, SemanticRole.LEARNED)
                or parent_column.role == SemanticRole.AGGREGATE):
            continue

        parent, child = frames[op.parent_table], frames[table_name]
        raw_bound = child[op.child_key].map(parent.set_index(rel.parent_key)[op.parent_column])
        temporal = column.type in (ColumnType.DATE, ColumnType.TIMESTAMP)
        if temporal:
            epoch = pd.Timestamp(0, tz="UTC")
            to_s = lambda s: (pd.to_datetime(s, format="mixed", utc=True, errors="coerce") - epoch).dt.total_seconds()
            bound, value = to_s(raw_bound), to_s(child[op.child_column])
        else:
            bound = pd.to_numeric(raw_bound, errors="coerce").astype(float)
            value = pd.to_numeric(child[op.child_column], errors="coerce").astype(float)

        upper_bounded = op.operator == "less_or_equal"  # child <= parent
        comparable = bound.notna() & value.notna()
        bad = comparable & ((value > bound) if upper_bounded else (value < bound))
        if not bad.any():
            continue

        # The far end of the allowed range. Numbers use the column's own declared or
        # sampled limit; dates use the typical gap seen on rows that already satisfy
        # the rule, so a redrawn delivery lands a plausible distance after its order.
        if temporal:
            ok = comparable & ~bad
            gaps = ((bound - value) if upper_bounded else (value - bound))[ok]
            gaps = gaps[gaps > 0]
            span = float(value.max() - value.min()) if value.notna().any() else 0.0
            delta = float(gaps.median()) if len(gaps) else max(span * 0.1, 86400.0)
            far = bound - delta if upper_bounded else bound + delta
        else:
            # Stay inside both the column's hard limit and its declared rule range, taking
            # the tighter. Using only the hard limit once turned shifts declared as 5-14
            # hours into 0-1 hours to satisfy a parent cap of 1 — silently overriding the
            # rule. When the two genuinely conflict, the rows are reported unsatisfiable.
            rule = column.rule
            limits = [column.minimum if upper_bounded else column.maximum]
            if rule is not None and rule.kind.value in ("integer_range", "number_range"):
                limits.append(rule.start if upper_bounded else rule.end)
            limits = [float(x) for x in limits if x is not None]
            if limits:
                declared = max(limits) if upper_bounded else min(limits)
            else:
                declared = float(value.min() if upper_bounded else value.max())
            far = pd.Series(declared, index=value.index)

        low, high = (far, bound) if upper_bounded else (bound, far)
        if column.type == ColumnType.INTEGER:
            low, high = np.ceil(low), np.floor(high)
        unsatisfiable = bad & (low > high)
        fix = bad & ~unsatisfiable
        n = int(fix.sum())
        if n:
            lo, hi = low[fix].to_numpy(), high[fix].to_numpy()
            if column.type == ColumnType.INTEGER:
                drawn = lo + np.floor(rng.random(n) * (hi - lo + 1))
                drawn = np.minimum(drawn, hi)
            else:
                drawn = lo + rng.random(n) * (hi - lo)
                decimals = column.rule.decimals if column.rule is not None else None
                if decimals is not None:
                    scale = 10 ** decimals
                    # round toward the inside of the range so rounding cannot re-break the rule
                    drawn = np.clip(np.round(drawn * scale) / scale, lo, hi)
            original = child[op.child_column]
            if temporal:
                stamps = pd.to_datetime(drawn, unit="s", utc=True)
                if pd.api.types.is_datetime64_any_dtype(original) and original.dt.tz is None:
                    stamps = stamps.tz_localize(None)
                if column.type == ColumnType.DATE:
                    # floor for an upper bound, ceil for a lower one, so the day never crosses it
                    stamps = stamps.floor("D") if upper_bounded else stamps.ceil("D")
                new = pd.Series(stamps, index=original.index[fix.to_numpy()])
            else:
                new = pd.Series(drawn, index=original.index[fix.to_numpy()])
                if column.type == ColumnType.INTEGER:
                    new = new.astype("int64")
            child.loc[fix, op.child_column] = new
        trace.append(dict(
            relationship=f"{table_name}.{op.child_column} {op.operator} {op.parent_table}.{op.parent_column}",
            column=op.child_column, repaired_rows=n, unsatisfiable_rows=int(unsatisfiable.sum()),
            method="redrawn uniformly within the range allowed by the parent value",
        ))
    return trace
