# Copyright 2024-2025 Arm Limited and/or its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import unittest

from typing import Callable, Tuple

import pytest

import torch
from executorch.backends.arm.test import common, conftest
from executorch.backends.arm.test.tester.arm_tester import ArmTester
from executorch.exir.backend.compile_spec_schema import CompileSpec
from parameterized import parameterized


test_data_generators = [
    # (test_name, test_data, dim)
    lambda: ("zeros", torch.zeros(10, 8, 5, 2), 0),
    lambda: ("zeros_neg_dim", torch.zeros(10, 7, 8, 9), -4),
    lambda: ("ones", torch.ones(10, 10), 1),
    lambda: ("ones_neg_dim", torch.ones(10, 3, 4), -1),
    lambda: ("rand", torch.rand(1, 2, 5, 8), 2),
    lambda: ("rand_neg_dim", torch.rand(2, 10, 8, 10), -2),
    lambda: ("randn", torch.randn(10, 10, 10, 10), 3),
    lambda: ("randn_neg_dim", torch.randn(10, 5, 8, 7), -3),
]

test_data_generators_FVP = [
    # (test_name, test_data, dim)
    lambda: ("ones", torch.ones(10, 10), 1),
    lambda: ("ones_neg_dim", torch.ones(10, 3, 4), -1),
    lambda: ("randn_neg_dim", torch.randn(1, 5, 8, 7), -3),
    lambda: ("zeros", torch.zeros(1, 8, 5, 2), 0),
    lambda: ("zeros_neg_dim", torch.zeros(1, 7, 8, 9), -4),
    lambda: ("rand", torch.rand(1, 2, 5, 8), 2),
    lambda: ("rand_neg_dim", torch.rand(1, 10, 8, 10), -2),
    lambda: ("randn", torch.randn(1, 10, 10, 10), 3),
]


class TestLogSoftmax(unittest.TestCase):
    """Tests logsoftmax."""

    class LogSoftmax(torch.nn.Module):
        def __init__(self, dim: int = -1):
            super().__init__()
            self.logsoftmax = torch.nn.LogSoftmax(dim=dim)

        def forward(self, x):
            return self.logsoftmax(x)

    def _test_logsoftmax_tosa_MI_pipeline(
        self, module: torch.nn.Module, test_data: Tuple[torch.tensor]
    ):
        (
            ArmTester(
                module,
                example_inputs=test_data,
                compile_spec=common.get_tosa_compile_spec("TOSA-0.80+MI"),
            )
            .export()
            .check(["torch.ops.aten.log_softmax.int"])
            .check_not(["torch.ops.quantized_decomposed"])
            .to_edge()
            .partition()
            .check_not(["executorch_exir_dialects_edge__ops_aten__logsoftmax_default"])
            .check_count({"torch.ops.higher_order.executorch_call_delegate": 1})
            .to_executorch()
            .run_method_and_compare_outputs(inputs=test_data)
        )

    def _test_logsoftmax_tosa_BI_pipeline(
        self, module: torch.nn.Module, test_data: Tuple[torch.tensor]
    ):
        (
            ArmTester(
                module,
                example_inputs=test_data,
                compile_spec=common.get_tosa_compile_spec("TOSA-0.80+BI"),
            )
            .quantize()
            .export()
            .check_not(["torch.ops.aten.log_softmax.int"])
            .check(["torch.ops.quantized_decomposed", "torch.ops.aten.mul.Tensor"])
            .to_edge()
            .partition()
            .check_not(["executorch_exir_dialects_edge__ops_aten__log_softmax_default"])
            .check_count({"torch.ops.higher_order.executorch_call_delegate": 1})
            .to_executorch()
            .run_method_and_compare_outputs(inputs=test_data, qtol=1)
        )

    def _test_logsoftmax_tosa_ethos_BI_pipeline(
        self,
        compile_spec: list[CompileSpec],
        module: torch.nn.Module,
        test_data: Tuple[torch.tensor],
    ):
        tester = (
            ArmTester(
                module,
                example_inputs=test_data,
                compile_spec=compile_spec,
            )
            .quantize()
            .export()
            .check_not(["torch.ops.aten.log_softmax.int"])
            .check(["torch.ops.quantized_decomposed", "torch.ops.aten.mul.Tensor"])
            .to_edge()
            .partition()
            .check_not(["executorch_exir_dialects_edge__ops_aten__logsoftmax_default"])
            .check_count({"torch.ops.higher_order.executorch_call_delegate": 1})
            .to_executorch()
            .serialize()
        )
        if conftest.is_option_enabled("corstone_fvp"):
            tester.run_method_and_compare_outputs(inputs=test_data, qtol=1)

    @parameterized.expand(test_data_generators)
    def test_logsoftmax_tosa_MI(self, test_data_generator: Callable[[], Tuple]):
        test_name, test_data, dim = test_data_generator()
        self._test_logsoftmax_tosa_MI_pipeline(self.LogSoftmax(dim=dim), (test_data,))

    @parameterized.expand(test_data_generators)
    @pytest.mark.flaky  # TODO: MLETORCH-460 - Numerically stabler (log)softmax implementation
    def test_logsoftmax_tosa_BI(self, test_data_generator: Callable[[], Tuple]):
        test_name, test_data, dim = test_data_generator()
        self._test_logsoftmax_tosa_BI_pipeline(self.LogSoftmax(dim=dim), (test_data,))

    @parameterized.expand(test_data_generators_FVP)
    @pytest.mark.flaky  # TODO: MLETORCH-460 - Numerically stabler (log)softmax implementation
    def test_logsoftmax_tosa_u55_BI(self, test_data_generator: Callable[[], Tuple]):
        test_name, test_data, dim = test_data_generator()
        self._test_logsoftmax_tosa_ethos_BI_pipeline(
            common.get_u55_compile_spec(), self.LogSoftmax(dim=dim), (test_data,)
        )

    @parameterized.expand(test_data_generators_FVP)
    @pytest.mark.flaky  # TODO: MLETORCH-460 - Numerically stabler (log)softmax implementation
    def test_logsoftmax_tosa_u85_BI(self, test_data_generator: Callable[[], Tuple]):
        test_name, test_data, dim = test_data_generator()
        self._test_logsoftmax_tosa_ethos_BI_pipeline(
            common.get_u85_compile_spec(), self.LogSoftmax(dim=dim), (test_data,)
        )
