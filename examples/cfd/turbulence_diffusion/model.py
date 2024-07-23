import torch
import math
import util

import matplotlib.pyplot as plt

from torchvision import utils
from torch.nn.parallel import DistributedDataParallel

from ema_pytorch import EMA
from denoising_diffusion_pytorch import Unet, GaussianDiffusion


def get_model(args, rank, world_size):
    # Setup Unet architecture, diffusion model, and exponential moving average
    model = Unet(
        dim=64,
        dim_mults=(1, 2, 4, 8, 16),
        channels=1,
        flash_attn=False  # On by default on an A100
    ).to(rank)

    diffusion = GaussianDiffusion(
        model,
        image_size=args.image_size,
        auto_normalize=True,  # Normalizes from [0, 1] to [-1, 1]
        timesteps=args.sample_timesteps
    ).to(rank)

    ema = None
    if rank == 0:
        ema = EMA(
            model=diffusion,
            beta=args.ema_beta,
            power=args.ema_power,
            update_every=args.update_ema_every
        ).to(rank)

    ddp_diffusion = DistributedDataParallel(diffusion, device_ids=[rank])

    if rank == 0:
        # util.show_random_datum(train_loader)
        total_params = sum(p.numel() for p in ddp_diffusion.parameters() if p.requires_grad)
        print(f'[{args.experiment_name}] [{rank}] Model has {total_params} parameters')

    return ddp_diffusion, ema


def sample(ema, args, epoch, experiment_path):
    ema.eval()
    with torch.inference_mode():
        sampled_images = ema.sample(
            batch_size=args.sample_size,
        )

        grid = utils.make_grid(
            sampled_images,
            nrow=math.ceil(math.sqrt(args.sample_size)),
            normalize=True
        )

        grid_np = grid.permute(1, 2, 0).cpu().numpy()
        plt.imsave(util.to_path(experiment_path, 'samples', f'sample_{epoch}.png'), grid_np, cmap='gray')

        print(f'[{args.experiment_name}] [{epoch}/{args.num_epochs}] Saved sample')
