import torch
from brainsim.memory.gated_memory import GatedMemoryConfig, TaskScopedMemory


def test_task_scoped_memory_prevents_cross_task_overwrite():
    m=TaskScopedMemory(GatedMemoryConfig(vocab=4,key_mode="token",max_tasks=2))
    for k,v in enumerate([1,2,3,0]): m.update("old",k,v,verified=True)
    for k,v in enumerate([2,3,0,1]): m.update("new",k,v,verified=True)
    assert [m.recall("old",k) for k in range(4)] == [1,2,3,0]
    assert [m.recall("new",k) for k in range(4)] == [2,3,0,1]


def test_unverified_update_can_be_blocked_and_task_cache_is_bounded():
    m=TaskScopedMemory(GatedMemoryConfig(vocab=4,key_mode="token",max_tasks=1,require_verified=True))
    assert not m.update("a",0,1,verified=False)["admitted"]
    m.update("a",0,1,verified=True); m.update("b",0,2,verified=True)
    assert m.task_count==1 and m.recall("a",0) is None and m.recall("b",0)==2


def test_gated_memory_state_roundtrip(tmp_path):
    m=TaskScopedMemory(GatedMemoryConfig(vocab=4,key_mode="token"))
    m.update("task",1,3,verified=True); p=tmp_path/"m.pt";m.save(p)
    n=TaskScopedMemory.load(p);assert n.recall("task",1)==3
