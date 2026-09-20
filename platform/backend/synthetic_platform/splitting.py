"""Holdout selection happens before the engine or data-dependent preparation."""
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from .verification import frame_hash


def split_source(source, evaluation, seed):
    target=evaluation.target
    if target not in source: raise ValueError('Utility target must exist in the original source.')
    eligible=source.dropna(subset=[target])
    if len(eligible)<12: raise ValueError('Utility evaluation needs at least 12 labelled records.')
    col=evaluation.split_column
    if evaluation.split=='group':
        if eligible[col].isna().any(): raise ValueError('Group split column contains missing values.')
        train_i,test_i=next(GroupShuffleSplit(n_splits=1,test_size=evaluation.test_fraction,random_state=seed).split(eligible,groups=eligible[col]))
        train,test=eligible.iloc[train_i],eligible.iloc[test_i]
    elif evaluation.split=='time':
        stamps=pd.to_datetime(eligible[col],format='mixed',utc=True,errors='coerce')
        if stamps.isna().any(): raise ValueError('Time split requires valid timestamps for every eligible row.')
        cutoff=stamps.sort_values().iloc[max(1,int(len(stamps)*(1-evaluation.test_fraction)))]
        train,test=eligible[stamps<cutoff],eligible[stamps>=cutoff]
    else:
        train,test=train_test_split(eligible,test_size=evaluation.test_fraction,random_state=seed,
            stratify=eligible[target] if evaluation.task=='classification' else None)
    if train.empty or test.empty: raise ValueError('Split produced an empty training or test partition.')
    return train.copy(),test.copy(),dict(strategy=evaluation.split,column=col,train_rows=len(train),test_rows=len(test),
        excluded_unlabelled_rows=len(source)-len(eligible),source_sha256=frame_hash(source),
        train_sha256=frame_hash(train),test_sha256=frame_hash(test),
        note='Generator fits training records only. User-declared policies and previously accepted schema assumptions are fixed inputs; no data-derived policy is independently validated by this score.')
