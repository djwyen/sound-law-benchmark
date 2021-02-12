from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import (ClassVar, Dict, Iterator, List, NewType, Optional,
                    Sequence, Set, Tuple, Union)

import numpy as np

import sound_law.data.data_loader as dl
import sound_law.rl.action as a
from dev_misc import BT, FT, LT, NDA, g, get_tensor
from dev_misc.devlib import pad_to_dense
from dev_misc.utils import (Singleton, cached_property,
                            is_main_process_and_thread)
from editdistance import eval_batch
from sound_law.data.alphabet import NULL_ID, PAD_ID, Alphabet

from .mcts_cpp import (PyST_CLL, PyST_CLR,  # pylint: disable=no-name-in-module
                       PyST_GBJ, PyST_GBW, PyST_NONE, PyST_VS, PyTreeNode,
                       parallel_gather_trajectory)

int2st = {
    PyST_CLL: 'CLL',
    PyST_CLR: 'CLR',
    PyST_NONE: None,
    PyST_VS: 'VS',
    PyST_GBJ: 'GBJ',
    PyST_GBW: 'GBW',
    NULL_ID: None  # This is used in STOP action.
}


# class VocabStateSpace:
#     """This is the factory class for creating VocabState."""

#     def get_state(self,
#                   seqs: Optional[dl.PaddedUnitSeqs] = None,
#                   ids: Optional[NDA] = None,
#                   lengths: Optional[NDA] = None,
#                   action_space: Optional[a.SoundChangeActionSpace] = None,
#                   end_state: Optional[VocabState] = None) -> VocabState:
#         if seqs is not None:
#             ids = seqs.ids.t()
#             lengths = seqs.lengths.t()
#         # NOTE(j_luo) Since memoryviews are used in the extension class, we have to make them contiguous.
#         arr = np.ascontiguousarray(ids.cpu().numpy())
#         lengths = np.ascontiguousarray(lengths.cpu().numpy())
#         state = VocabState(arr=arr, lengths=lengths, end_node=end_state)
#         if action_space is not None:
#             action_space.set_action_allowed(state)
#         return state


class VocabState(PyTreeNode):
    """State representing the vocab. Use `VocabStateSpace` to create one instance."""

    abc: ClassVar[Alphabet] = None

    @cached_property
    def tensor(self) -> LT:
        """Convert the state into a long tensor."""
        return get_tensor(self.vocab_array).rename('word', 'pos')  # t().contiguous().rename('pos', 'word')

    @property
    def q(self):
        return self.total_values / (1e-8 + self.action_counts)

    @property
    def word_list(self) -> List[str]:
        assert self.abc is not None
        words = list()
        for id_seq in self.vocab:
            words.append(''.join(self.abc[i] for i in id_seq[1:-1]))  # pylint: disable=unsubscriptable-object
        return words

    @property
    def segment_list(self) -> List[List[str]]:
        assert self.abc is not None
        words = list()
        for id_seq in self.vocab:
            words.append([self.abc[i] for i in id_seq])  # pylint: disable=unsubscriptable-object
        return words


@dataclass
class TrEdge:
    """This represents one edge in the trajectories."""
    step: int
    s0: VocabState
    a: a.SoundChangeAction
    pa: NDA
    r: float
    qs: NDA
    s1: VocabState
    mcts_pi: NDA
    # mcts_pi: Optional[NDA] = None  # This stores the policy produced by MCTS.
    # rtg: Optional[float] = None


# class BaseTrajectory:

#     def __init__(self, init_state: VocabState, end_state: VocabState):
#         self._states = [init_state]
#         self._actions: List[a.SoundChangeAction] = list()
#         self._rewards: List[float] = list()
#         self._mcts_pis: List[NDA] = list()
#         self._end_state = end_state
#         self._done = False  # Whether the trajectory has reached the end state.

#     @property
#     def rewards(self) -> NDA:
#         return np.asarray(self._rewards, dtype='float32')

#     @property
#     def done(self) -> bool:
#         return self._done

#     @property
#     def latest_state(self) -> VocabState:
#         return self._states[-1]

#     def __len__(self):
#         return len(self._actions)

#     def __iter__(self) -> Iterator[TrEdge]:
#         for i, (s0, a, r) in enumerate(zip(self._states, self._actions, self._rewards)):
#             s1 = self._states[i + 1]
#             done = False if i < len(self._actions) - 1 else self._done
#             mcts_pi = self._mcts_pis[i] if self._mcts_pis else None
#             yield TrEdge(i, s0, a, s1, done, r, mcts_pi=mcts_pi)

#     def __repr__(self):
#         out = list()
#         for edge in self:
#             out.append(f'({edge.a}; {edge.r:.3f})')
#         out = ', '.join(out)
#         if self._done:
#             out += ' DONE'
#         return out

#     def save(self, log_dir: str):
#         with open(Path(log_dir) / 'path.txt', 'w', encoding='utf8') as fout:
#             for edge in self:
#                 fout.write(str(edge.a) + '\n')


# class Trajectory(BaseTrajectory):
class Trajectory:

    def __init__(self, last_state: VocabState):
        # NOTE(j_luo) They have different batch size. `id_seqs` has n + 1, `rewards` has n (last state doesn't have any q due to being unexplored), while the remaining tree have 7 * n each.
        self.id_seqs, self.actions, self.rewards, self.permissible_actions, self.mcts_pis, self.qs = parallel_gather_trajectory(
            last_state, g.num_workers)
        self.done = last_state.done
        self._num_edges = len(self.id_seqs) - 1
        assert len(self.rewards) == len(self.id_seqs) - 1
        assert len(self.actions) == len(self.permissible_actions) == len(
            self.mcts_pis) == len(self.qs) == 7 * self._num_edges

    def __len__(self):
        return self._num_edges

    def __iter__(self) -> Iterator[TrEdge]:
        for i in range(self._num_edges):
            s0 = self.id_seqs[i]
            s1 = self.id_seqs[i + 1]
            start = 7 * i
            end = start + 7
            r = self.rewards[i]
            action = a.SoundChangeAction(self.actions[start], self.actions[start + 2], self.actions[start + 3], self.actions[start + 4],
                                         self.actions[start + 5], self.actions[start + 6], special_type=int2st[self.actions[start + 1]])
            qs = self.qs[start:end]
            pa = self.permissible_actions[start: end]
            mcts_pi = self.mcts_pis[start: end]
            yield TrEdge(i, s0, action, pa, r, qs, s1, mcts_pi)
        # for i, (s0, a, r) in enumerate(zip(self.id_seqs, self.rewards, self.permissible_actions, self.mcts_pis)):
        #     s1 = self.id_seqs[i + 1]
        #     # done = False if i < len(self._actions) - 1 else self._done
        #     mcts_pi = self.mcts_pis[i] if self.mcts_pis else None
        #     yield TrEdge(i, s0, a, s1, done, r, mcts_pi=mcts_pi)

    # def append(self,
    #            action: a.SoundChangeAction,
    #            state: VocabState,
    #            reward: float,
    #            mcts_pi: Optional[NDA] = None):
    #     if self._done:
    #         raise RuntimeError(f'This trajectory has already ended.')

    #     self._actions.append(action)
    #     self._states.append(state)
    #     self._rewards.append(reward)
    #     if mcts_pi is not None:
    #         self._mcts_pis.append(mcts_pi)
    #     self._done = state.done if state is not None else False


# class ReplayTrajectory(BaseTrajectory):

#     def __init__(self, tr: Trajectory):
#         self._states = [state.detach() for state in tr._states]
#         self._actions = tr._actions
#         self._rewards = tr._rewards
#         self._mcts_pis = tr._mcts_pis
#         self._end_state = tr._end_state
#         self._done = tr._done
