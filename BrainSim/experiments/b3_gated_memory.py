"""B3 baseline: compare shared token memory with task-scoped gated memory.

The experiment is synthetic and deliberately small. It tests whether isolating per-task fast
associations prevents a new rule from overwriting the old task's associations. It does not test
rule induction or language learning.
Run from BrainSim/: python -m experiments.b3_gated_memory [--seeds 0,1,2]
"""
from __future__ import annotations
import argparse,json,statistics,time
from pathlib import Path
import torch
from brainsim.environment.sequence_tasks import SequenceConfig,make_rules
from brainsim.memory.fast_memory import FastAssociativeMemory,FastMemoryConfig
from brainsim.memory.gated_memory import GatedMemoryConfig,TaskScopedMemory

ROOT=Path(__file__).resolve().parent.parent

def accuracy(mem,task,rule,mode):
    correct=0
    for key,target in enumerate(rule):
        if mode=="shared":
            pred = int(mem.scores(torch.tensor([key]))[0].argmax()) if bool(mem.seen(torch.tensor([key]))[0]) else None
        else:
            pred = mem.recall(task,key)
        correct += pred==target
    return correct/len(rule)

def run_seed(seed:int)->dict:
    cfg=SequenceConfig(seed=seed)
    rules=make_rules(cfg)
    old_rule=rules.train[0]; new_rule=rules.heldout[0]
    shared=FastAssociativeMemory(FastMemoryConfig(vocab=cfg.vocab,key_mode="token"))
    for key,target in enumerate(old_rule): shared.update(torch.tensor([key]),torch.tensor([target]))
    old_before=accuracy(shared,"shared",old_rule,"shared")
    # A task switch overwrites token associations in the single shared table.
    for key,target in enumerate(new_rule): shared.update(torch.tensor([key]),torch.tensor([target]))
    shared_old=accuracy(shared,"shared",old_rule,"shared")
    shared_new=accuracy(shared,"shared",new_rule,"shared")
    gated=TaskScopedMemory(GatedMemoryConfig(vocab=cfg.vocab,key_mode="token",max_tasks=4,
                                             min_surprise=.8,require_verified=False))
    for key,target in enumerate(old_rule): gated.update("old",key,target,verified=True)
    gated_old_before=accuracy(gated,"old",old_rule,"gated")
    for key,target in enumerate(new_rule): gated.update("new",key,target,verified=True)
    gated_old=accuracy(gated,"old",old_rule,"gated")
    gated_new=accuracy(gated,"new",new_rule,"gated")
    return {"seed":seed,"shared_old_before":old_before,"shared_old_after_switch":shared_old,
            "shared_new":shared_new,"gated_old_before":gated_old_before,
            "gated_old_after_switch":gated_old,"gated_new":gated_new}

def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",default="0,1,2");a=p.parse_args()
    seeds=[int(x) for x in a.seeds.split(",") if x]; runs=[run_seed(s) for s in seeds]
    keys=["shared_old_before","shared_old_after_switch","shared_new","gated_old_before","gated_old_after_switch","gated_new"]
    summary={k:statistics.mean(r[k] for r in runs) for k in keys}
    out={"experiment":"B3 task-scoped memory gate vs shared token memory","generated":time.strftime("%Y-%m-%dT%H:%M:%S"),
         "hypothesis":"task-scoped memory prevents cross-task overwrite while retaining task-local associations",
         "task":"two disjoint permutation rules; all token transitions observed in each task",
         "runs":runs,"summary":summary,"limits":["synthetic lookup task","does not test rule induction",
         "does not test learned gate generalization","task identity is supplied externally"]}
    path=ROOT/"experiments"/"results"/"b3_gated_memory.json";path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));print(f"wrote {path}")
if __name__=="__main__":main()
