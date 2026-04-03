import os, psutil
from datetime import datetime, timezone
from cayleypy import CayleyGraph, PermutationGroups
import torch


def test_workload(n):
    now = datetime.now(timezone.utc)
    print(f'Starting test workload on S_{n} at {now:%H:%M:%S UTC}.', flush=True)
    cg_def = PermutationGroups.coxeter(n)
    cg = CayleyGraph(cg_def)
    now = datetime.now(timezone.utc)
    print(f'Starting BFS on S_{n} at {now:%H:%M:%S UTC}.', flush=True)
    bfs_result = cg.bfs()
    now = datetime.now(timezone.utc)
    print(f'Finished BFS on S_{n} at {now:%H:%M:%S UTC}.', flush=True)
    return bfs_result.diameter()


def main():
    print("CUDA device count:", torch.cuda.device_count(), flush=True)
    print("CUDA_VISIBLE_DEVICES:", os.environ.get("CUDA_VISIBLE_DEVICES"), flush=True)
    for n in range(2, 15):
        torch.cuda.empty_cache()
        # print('GPU memory before starting:\n'
        #       f'cur_gpu_mem_all={torch.cuda.memory_allocated()} '
        #       f'cur_gpu_mem_res={torch.cuda.memory_reserved()} '
        #       f'peak_gpu_mem_all={torch.cuda.max_memory_allocated()} '
        #       f'peak_gpu_mem_res={torch.cuda.max_memory_reserved()}',
        #       flush=True
        #       )
        # torch.cuda.reset_peak_memory_stats()
        try:
            d = test_workload(n)
            p = psutil.Process(os.getpid())
            print(f'Test workload returned diam={d}.'
                  # f'Exec details: pid={p.pid} threads={p.num_threads()}\n'
                  # f'cur_gpu_mem_all={torch.cuda.memory_allocated()} '
                  # f'cur_gpu_mem_res={torch.cuda.memory_reserved()} '
                  # f'peak_gpu_mem_all={torch.cuda.max_memory_allocated()} '
                  # f'peak_gpu_mem_res={torch.cuda.max_memory_reserved()}'
                  , flush=True)
        except Exception as e:
            now = datetime.now(timezone.utc)
            print(f'Calculation failed at {now:%H:%M:%S UTC}, exception:\n{e}')


if __name__ == '__main__':
    main()