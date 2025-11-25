from __future__ import annotations

from xdsl.ir import Attribute, Dialect, Region, SSAValue
from xdsl.irdl import (
    IRDLOperation,
    irdl_op_definition,
    region_def,
    traits_def,
    var_operand_def,
    var_result_def,
)
from xdsl.traits import HasParent, IsolatedFromAbove, IsTerminator, ReturnLike
from xdsl.utils.exceptions import VerifyException


@irdl_op_definition
class ComputeOp(IRDLOperation):
    """
    A compute operation that defines a region isolated from above.

    It takes arguments (operands) and returns results.
    Inside the region, a Single-Static Use (SSU) constraint is enforced:
    Every value defined in the region (Block Arguments and Operation Results)
    must be used at most once.
    """

    name = "ssu.compute"

    arguments = var_operand_def()
    res = var_result_def()
    body = region_def()

    traits = traits_def(IsolatedFromAbove())

    assembly_format = (
        "attr-dict `(` ($arguments^ `:` type($arguments))? `)` `:` type($res) $body"
    )

    def __init__(
        self, operands: list[SSAValue], result_types: list[Attribute], region: Region
    ):
        super().__init__(
            operands=[operands], result_types=[result_types], regions=[region]
        )

    def verify_(self) -> None:
        assert self.body.first_block is not None
        if self.body.first_block.arg_types != self.arguments.types:
            raise VerifyException(
                f"Block arguments ({', '.join(str(x) for x in self.body.first_block.arg_types)}) do not match the operation's "
                f"arguments ({', '.join(str(x) for x in self.arguments.types)})."
            )

        # Helper to verify SSU constraint
        def check_single_use(val: SSAValue, description: str):
            if val.has_more_than_one_use():
                raise VerifyException(
                    f"{description} is used more than once. This violates the single static use constraint."
                )

        # Iterate over every block in the region
        for i, block in enumerate(self.body.blocks):
            # 1. Verify Block Arguments (values defined at block entry)
            for arg_idx, arg in enumerate(block.args):
                check_single_use(arg, f"Block argument {arg_idx} in block {i}")

            # 2. Verify Operation Results (values defined by ops inside the block)
            for op in block.ops:
                for res_idx, res in enumerate(op.results):
                    check_single_use(
                        res,
                        f"Result {res_idx} of operation '{op.name}' inside compute region",
                    )


@irdl_op_definition
class YieldOp(IRDLOperation):
    """
    Terminates the ssu.compute region and yields values to the parent operation.
    """

    name = "ssu.yield"

    arguments = var_operand_def()

    traits = traits_def(HasParent(ComputeOp), IsTerminator(), ReturnLike())

    assembly_format = "attr-dict ($arguments^ `:` type($arguments))?"

    def __init__(self, *operands: SSAValue):
        super().__init__(operands=[operands])

    def verify_(self) -> None:
        compute_op = self.parent_op()
        assert isinstance(compute_op, ComputeOp)

        compute_return_types = compute_op.res.types
        yield_types = self.arguments.types
        if compute_return_types != yield_types:
            raise VerifyException(
                "Expected arguments to have the same types as the compute operation's results"
            )


SSU = Dialect(
    "ssu",
    [
        ComputeOp,
        YieldOp,
    ],
)
