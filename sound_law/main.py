from typing import Optional

import torch

from dev_misc import Initiator, add_argument, g, parse_args
from dev_misc.devlib.named_tensor import patch_named_tensors
from dev_misc.trainlib import set_random_seeds
from sound_law.config import reg
from sound_law.train.manager import OnePairManager, OneToManyManager

add_argument('task', dtype=str, default='one_pair', choices=['one_pair', 'one_to_many'], msg='Which task to execute.')

import json

def setup() -> Initiator:
    initiator = Initiator(reg, logger=True, log_level=True, gpus=True, random_seed=True, commit_id=True, log_dir=True)
    patch_named_tensors()
    torch.set_printoptions(sci_mode=False)
    return initiator


def main(initiator: Initiator):
    initiator.run()
    if g.task == 'one_pair':
        manager = OnePairManager()
    else:
        manager = OneToManyManager()
    manager.run()


if __name__ == '__main__':
    initiator = setup()
    main(initiator)
