"""Small clip-level crash classifier used only by Module 2.

Inputs are 16 RGB frames sampled at four frames/second and resized to
160x96. The network receives both appearance and frame-difference channels.
"""
from pathlib import Path

import numpy as np
import torch
from torch import nn


class TemporalAccidentNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv3d(6, 16, kernel_size=(3, 5, 5), stride=(1, 2, 2), padding=(1, 2, 2), bias=False),
            nn.BatchNorm3d(16), nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 2, 2)),
            nn.Conv3d(16, 32, kernel_size=3, stride=(2, 2, 2), padding=1, bias=False),
            nn.BatchNorm3d(32), nn.ReLU(inplace=True),
            nn.Conv3d(32, 64, kernel_size=3, stride=(2, 2, 2), padding=1, bias=False),
            nn.BatchNorm3d(64), nn.ReLU(inplace=True),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Linear(64 * 4, 64), nn.ReLU(inplace=True),
            nn.Dropout(p=0.25), nn.Linear(64, 1),
        )

    def forward(self, rgb):
        if rgb.ndim != 5:
            raise ValueError('Expected RGB clip tensor [batch, time, channels, height, width].')
        if rgb.shape[1] != 16 or rgb.shape[2] != 3:
            raise ValueError('Expected 16 RGB frames per clip.')
        # Explicit motion signal, without reducing the task to overlap or a
        # single-frame displacement threshold.
        differences = torch.abs(rgb[:, 1:] - rgb[:, :-1])
        differences = torch.cat((differences[:, :1], differences), dim=1)
        clip = torch.cat((rgb, differences), dim=2).permute(0, 2, 1, 3, 4).contiguous()
        features = self.features(clip)
        # With 16 inputs and two temporal stride-2 layers this is [B,64,4,H,W].
        # A direct spatial mean is supported by Apple MPS, unlike adaptive
        # 3D pooling on the installed PyTorch build.
        features = features.mean(dim=(3, 4))
        return self.classifier(features).squeeze(1)


def load_temporal_model(path, device='cpu'):
    path = Path(path)
    if not path.is_file():
        return None, None
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    model = TemporalAccidentNet().to(device)
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    return model, float(checkpoint['threshold'])


@torch.inference_mode()
def score_rgb_frames(model, frames, device='cpu'):
    """Return a single sigmoid score for a sequence of 16 uint8 RGB frames."""
    array = np.asarray(frames, dtype=np.uint8)
    if array.shape[0] != 16 or array.ndim != 4 or array.shape[-1] != 3:
        raise ValueError('Expected [16, height, width, 3] uint8 RGB frames.')
    clip = torch.from_numpy(np.ascontiguousarray(array)).to(device=device, dtype=torch.float32)
    clip = clip.permute(0, 3, 1, 2).unsqueeze(0).div_(255.0)
    return float(torch.sigmoid(model(clip))[0].item())
