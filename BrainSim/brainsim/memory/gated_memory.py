"""Task-scoped fast memory with admission and task-switch gating (B3 baseline).

Each task owns an isolated associative memory. Updates require verification or sufficient surprise;
retrieval is always scoped to the requested task. The cache is bounded and uses LRU eviction.
This is a simple baseline, not a claim of optimal gating.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import time
import torch
from brainsim.memory.fast_memory import FastAssociativeMemory, FastMemoryConfig

@dataclass(frozen=True)
class GatedMemoryConfig:
    vocab: int
    key_mode: str = "pair"
    max_tasks: int = 8
    min_surprise: float = 0.8
    require_verified: bool = False
    blend: float = 0.9

    def __post_init__(self):
        if self.max_tasks < 1 or self.min_surprise < 0:
            raise ValueError("max_tasks must be >=1 and min_surprise >=0")

class TaskScopedMemory:
    def __init__(self, cfg: GatedMemoryConfig):
        self.cfg=cfg; self._tasks: dict[str, tuple[FastAssociativeMemory,float]]={}

    @property
    def task_count(self) -> int: return len(self._tasks)

    def _get(self, task_id: str, create: bool) -> FastAssociativeMemory | None:
        if task_id in self._tasks:
            mem,_=self._tasks[task_id]; self._tasks[task_id]=(mem,time.monotonic()); return mem
        if not create: return None
        if len(self._tasks)>=self.cfg.max_tasks:
            oldest=min(self._tasks,key=lambda k:self._tasks[k][1]); del self._tasks[oldest]
        mem=FastAssociativeMemory(FastMemoryConfig(vocab=self.cfg.vocab,key_mode=self.cfg.key_mode,
            blend=self.cfg.blend))
        self._tasks[task_id]=(mem,time.monotonic()); return mem

    def update(self, task_id: str, key: int, target: int, *, prev: int | None = None,
               verified: bool = False) -> dict:
        if self.cfg.require_verified and not verified:
            return {"admitted":False,"surprise":None,"reason":"verification required"}
        mem=self._get(task_id,True)
        keys=torch.tensor([key]); vals=torch.tensor([target]); prev_t=torch.tensor([prev]) if prev is not None else None
        if mem.seen(keys,prev_t)[0]:
            before=mem.probabilities(keys,prev_t)[0]
            surprise=float((torch.nn.functional.one_hot(vals[0],self.cfg.vocab).float()-before).norm())
        else:
            surprise=1.0
        if not verified and surprise < self.cfg.min_surprise:
            return {"admitted":False,"surprise":surprise,"reason":"below surprise threshold"}
        observed=mem.update(keys,vals,prev=prev_t)[0]
        return {"admitted":True,"surprise":observed,"reason":"verified" if verified else "surprise gate"}

    def recall(self, task_id: str, key: int, *, prev: int | None = None) -> int | None:
        mem=self._get(task_id,False)
        if mem is None: return None
        keys=torch.tensor([key]); prev_t=torch.tensor([prev]) if prev is not None else None
        if not bool(mem.seen(keys,prev_t)[0]): return None
        return int(mem.scores(keys,prev_t)[0].argmax())

    def reset(self, task_id: str | None = None) -> None:
        if task_id is None: self._tasks.clear()
        else: self._tasks.pop(task_id,None)

    def save(self,path: str|Path) -> Path:
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        torch.save({"config":asdict(self.cfg),"tasks":{k:{"M":m.M,"counts":m.counts,
            "config":asdict(m.cfg),"last":last} for k,(m,last) in self._tasks.items()}},path)
        return path

    @classmethod
    def load(cls,path: str|Path) -> "TaskScopedMemory":
        data=torch.load(path,map_location="cpu",weights_only=True); obj=cls(GatedMemoryConfig(**data["config"]))
        for task,row in data["tasks"].items():
            mem=FastAssociativeMemory(FastMemoryConfig(**row["config"]))
            mem.M.copy_(row["M"]); mem.counts.copy_(row["counts"])
            obj._tasks[task]=(mem,float(row["last"]))
        return obj
