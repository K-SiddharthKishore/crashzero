import numpy as np
import pytest

torch = pytest.importorskip('torch')

from module_2_accident_response.temporal import TemporalAccidentNet, score_rgb_frames


def test_temporal_model_emits_one_logit_per_clip():
    model = TemporalAccidentNet().eval()
    with torch.inference_mode():
        output = model(torch.zeros((2, 16, 3, 96, 160)))
    assert output.shape == (2,)


def test_temporal_model_rejects_non_temporal_input():
    with pytest.raises(ValueError, match='16 RGB frames'):
        TemporalAccidentNet()(torch.zeros((1, 8, 3, 96, 160)))


def test_temporal_scoring_requires_fixed_rgb_clip():
    model = TemporalAccidentNet().eval()
    with pytest.raises(ValueError, match=r'Expected \[16, height, width, 3\]'):
        score_rgb_frames(model, np.zeros((15, 96, 160, 3), dtype=np.uint8))


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason='Apple MPS is unavailable')
def test_temporal_model_supports_mps_training_step():
    model = TemporalAccidentNet().to('mps').train()
    clips = torch.rand((2, 16, 3, 96, 160), device='mps')
    labels = torch.tensor([0.0, 1.0], device='mps')
    loss = torch.nn.BCEWithLogitsLoss()(model(clips), labels)
    loss.backward()
    assert torch.isfinite(loss).item()
    assert next(model.parameters()).grad is not None
