import os
import socket
import torch
import torch.distributed as dist

def main():
    dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    world = dist.get_world_size()

    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    torch.cuda.set_device(local_rank)

    # tiny collective to prove NCCL works
    x = torch.tensor([rank], device="cuda")
    dist.all_reduce(x, op=dist.ReduceOp.SUM)

    free, total = torch.cuda.mem_get_info()
    host = socket.gethostname()

    if rank == 0:
        print(f"[rank0] host={host} world={world} torch={torch.__version__}")
        print(f"[rank0] all_reduce sum(0..{world-1}) = {x.item()} (expect {world*(world-1)//2})")

    print(f"[rank {rank:02d}] local_rank={local_rank} gpu={torch.cuda.current_device()} "
          f"free={free/1e9:.1f}GB total={total/1e9:.1f}GB",
          flush=True)

    dist.destroy_process_group()

if __name__ == "__main__":
    main()