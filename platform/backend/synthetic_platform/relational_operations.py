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
        bad=(value>bound) if op.operator=='less_or_equal' else (value<bound)
        if op.missing=='fail': bad |= missing
        checks.append(dict(relationship=f'{op.child_table}.{op.child_column} {op.operator} {op.parent_table}.{op.parent_column}',
            passed=not bad.any(),failing_rows=int(bad.sum()),skipped_rows=int(missing.sum()) if op.missing=='skip' else 0))
    return checks
