import pytest

from btm.harness.model import AzureModel


def test_the_real_model_does_not_expose_temperature() -> None:
    assert AzureModel().supports_temperature is False


def test_setting_a_temperature_is_refused() -> None:
    with pytest.raises(ValueError, match="no admite temperature"):
        AzureModel(temperature=0.0)
