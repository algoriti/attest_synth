"""Checks over final artifacts, independent of the generating adapter."""
import hashlib
import pandas as pd
import numpy as np
from .spec import ColumnType


def frame_hash(frame):
    return hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()


def schema_checks(frame, table):
    checks = []
    def add(kind, columns, bad, detail):
        checks.append(dict(operator=kind, columns=columns, passed=bad == 0,
                           failing_rows=int(bad), detail=detail))
    for c in table.columns:
        if c.name not in frame:
            add('schema', [c.name], max(1,len(frame)), 'Missing column')
            continue
        v=frame[c.name]
        if not c.nullable:
            add('not_null', [c.name], v.isna().sum(), 'Required by schema')
        present=v.dropna()
        bad=0
        if c.type in (ColumnType.NUMBER,ColumnType.INTEGER):
            n=pd.to_numeric(present,errors='coerce')
            invalid=~np.isfinite(n.astype(float))
            if c.type == ColumnType.INTEGER: invalid |= n != np.round(n)
            if c.minimum is not None: invalid |= n < c.minimum
            if c.maximum is not None: invalid |= n > c.maximum
            bad=int(invalid.sum())
        elif c.type == ColumnType.BOOLEAN:
            bad=int((~present.map(lambda x: isinstance(x,(bool,np.bool_)))).sum())
        elif c.type in (ColumnType.DATE,ColumnType.TIMESTAMP):
            bad=int(pd.to_datetime(present,format='mixed',utc=True,errors='coerce').isna().sum())
        elif c.type == ColumnType.UUID:
            import uuid
            def valid(x):
                try: uuid.UUID(str(x)); return True
                except (ValueError,TypeError): return False
            bad=int((~present.map(valid)).sum())
        elif c.type == ColumnType.STRING:
            bad=int((~present.map(lambda x:isinstance(x,str))).sum())
        add('schema', [c.name], bad, f'Type and bounds: {c.type.value}')
        if c.allowed_values is not None:
            add('in_set',[c.name],(~present.isin(c.allowed_values)).sum(),'Allowed values from schema')
    keys=list(table.unique_keys)
    if table.primary_key: keys.append([table.primary_key])
    for key in keys:
        if all(c in frame for c in key):
            bad=frame[key].isna().any(axis=1) | frame.duplicated(key)
            add('unique_key',key,bad.sum(),'Key must be present and unique')
    return checks


def relationship_checks(spec, frames):
    results=[]
    for rel in spec.relationships:
        parent,child=frames[rel.parent_table],frames[rel.child_table]
        keys=child[rel.child_key]
        bad=(keys.notna() & ~keys.isin(parent[rel.parent_key])) | (keys.isna() & (not rel.optional))
        counts=keys.value_counts().reindex(parent[rel.parent_key],fill_value=0)
        low=rel.child_count_min if rel.child_count_min is not None else 0
        high=1 if rel.cardinality=='one_to_one' else rel.child_count_max
        count_bad=counts < low
        if high is not None: count_bad |= counts > high
        results.append(dict(relationship=f'{rel.parent_table} → {rel.child_table}',
            passed=not bad.any() and not count_bad.any(), invalid_keys=int(bad.sum()),
            parents_outside_bounds=int(count_bad.sum())))
    return results
