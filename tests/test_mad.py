import pytest
import numpy as np


def mad_detect(data):
    arr = np.array(data)
    median_val = np.median(arr)
    mad = np.median(np.abs(arr - median_val))
    score = abs((arr[-1] - median_val) / (1.4826 * mad))
    return score


def test_normal_data():
    # 正常平稳时序，得分偏低
    res = mad_detect([10, 11, 9, 10, 11])
    assert res < 3


def test_abnormal_spike():
    # 突发尖刺，异常得分高
    res = mad_detect([10, 11, 9, 10, 80])
    assert res > 3
