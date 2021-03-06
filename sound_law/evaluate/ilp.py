from __future__ import annotations

import bisect
import logging
import pickle
import random
import re
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, Set, Union

import pandas as pd
from ortools.linear_solver import pywraplp

# from sound_law.rl.env import ToyEnv
# from sound_law.rl.mcts_cpp import \
#     PyNull_abc  # pylint: disable=no-name-in-module
# from sound_law.rl.trajectory import VocabState
import sound_law.rl.rule as rule
from dev_misc import add_argument, g
from sound_law.main import setup
# from sound_law.data.alphabet import Alphabet
from sound_law.rl.action import SoundChangeAction
from sound_law.rl.rule import HandwrittenRule


class ToyEnv():

    def __init__(self, start_state):
        self.start = start_state

    def apply_action(self, state, act):
        # somehow apply action to state
        new_state = state
        return new_state

    def apply_block(self, state, block):
        '''Applies a block of actions in order'''
        for act in block:
            state = self.apply_action(state, act)
        return state

    def get_state_edit_dist(self, state1, state2):
        # somehow compute the edit distance between these two states
        return (random.random() + 1) * random.randint(1, 20)

    # def compare_effects(self, act1, act2, state):
    #     state1 = self.apply_action(state, act1)
    #     state2 = self.apply_action(state, act2)
    #     return self.get_state_edit_dist(state1, state2)


def read_rules_from_txt(filename: str) -> List[SoundChangeAction]:
    '''Reads rules from a given file. Currently assuming file is a list of rules with commas at the end, formatted the same way test_annotations.csv is with [ruletype]: a > b / [context] _ [context], eg basic: z > ∅ / [+syllabic] r _ # '''
    rules = []
    with open(filename, 'r') as f:
        for line in f:
            rules.append(HandwrittenRule.from_str(line).to_action())
    return rules


def match_rulesets(gold: List[List[SoundChangeAction]],
                   cand: List[SoundChangeAction],
                   env: SoundChangeEnv,
                   match_proportion: float = .7,
                   k_matches: int = 10) -> List[List[Int, List[Int]]]:
    '''Finds the optimal matching of rule blocks in the gold ruleset to 0, 1, or 2 rules in the candidate ruleset. Frames the problem as an integer linear program. Returns a list of tuples with the matching.'''

    solver = pywraplp.Solver.CreateSolver('SCIP')  # TODO investigate other solvers
    # form the different variables in this ILP
    # this dict maps strings to pointers to the variable that string represents. Makes things much more readable.
    v = {}
    # this dict maps rules/blocks to their individual constraint: eg 'gold_0' for the constraint for the 0th gold block, or 'cand_3' for the 3th candidate rule.
    c = {}

    # initialize constraints for all blocks/rules
    # constraint is of form a_i0 + ... + a_im + b_i(01) + ... <= 1
    # cand constraint is of form a_0i + ... + a_ni + b_0(0i) + ... + b_0(in) <= 1
    # one such constraint exists for each gold block/cand rule. Only one of the variables a/b can be equal to 1, so only one matching occurs, if any
    for i in range(len(gold)):
        c['gold_' + str(i)] = solver.Constraint(0, 1)
    for j in range(len(cand)):
        c['cand_' + str(j)] = solver.Constraint(0, 1)

    # finally, this matching constraint forces the model to match at least some of the rules (otherwise it would just match no rules to vacuously achieve a minimum objective of 0)
    # it stipulates that the sum of all variables must be >= some minimum match number
    # by the handshake lemma, only a constraint needs to be placed on gold — this implies some amount of matching with candidate
    # we will update the actual bounds later based on how many gold blocks are actually active in this vocab, i.e. how many gold blocks actually apply to one or more words in the vocab
    c['min_match'] = solver.Constraint(0, 1)
    number_active_gold_blocks = 0  # counts the number of gold blocks eligible for matching, ie rules that actually change words

    curr_state = env.start
    objective = solver.Objective()
    for i in range(len(gold)):
        # as an optimization, we only create variables for the best k_matches that a given gold block has with collections of rules in candidate. We assume that matchings with higher cost would never be chosen anyway and won't affect the solution, so they can just be excluded from the linear program.
        highest_cost = None
        # entries are of form (varname, i, [j...k], cost) — ie the variable pairing i with rules [j...k] has cost coefficient cost. Costs are in increasing order.
        paired_costs = []
        block = gold[i]
        # print('block', i, block)
        try:
            gold_state = env.apply_block(curr_state, block)
        except RuntimeError:
            # this block in gold doesn't actually apply to any items, causing the RuntimeError
            # it's nonsensical to discuss what rules are most similar to a block that does nothing so we skip this block: we don't match it with anything, and we don't even give it a variable for the ILP
            pass
        else:
            number_active_gold_blocks += 1
            # actually loop over the variables and create variables for this block

            for j in range(len(cand)):
                rule = cand[j]
                a_var_name = 'a_' + str(i) + ',(' + str(j) + ')'
                # print('cand:', j, rule)

                # TODO(djwyen) add try/excepts to each other application of apply_action
                try:
                    cand_state = env.apply_action(curr_state, rule)
                except RuntimeError:
                    # this rule doesn't change anything, ie it has zero application sites. That causes the RuntimeError to be thrown.
                    # exclude this rule from consideration since it shouldn't be matched
                    pass
                else:
                    cost = env.get_state_edit_dist(gold_state, cand_state)
                    new_tuple = (a_var_name, i, [j], cost)

                    # add this cost to the list if it's better than what we currently have
                    if len(paired_costs) < k_matches or cost < highest_cost:
                        if len(paired_costs) == k_matches:
                            del paired_costs[-1]
                        bisect.insort_left(paired_costs, new_tuple)  # insert in sorted order
                        highest_cost = paired_costs[-1][3]  # update costs

            for j in range(len(cand)):
                rule1 = cand[j]
                for k in range(j + 1, len(cand)):
                    rule2 = cand[k]
                    b_var_name = 'b_' + str(i) + ',(' + str(j) + ',' + str(k) + ')'

                    try:
                        cand_state = env.apply_block(curr_state, [rule1, rule2])
                    except RuntimeError:
                        pass
                    else:
                        cost = env.get_state_edit_dist(gold_state, cand_state)
                        new_tuple = (b_var_name, i, [j, k], cost)

                        if len(paired_costs) < k_matches or cost < highest_cost:
                            if len(paired_costs) == k_matches:
                                del paired_costs[-1]
                            bisect.insort_left(paired_costs, new_tuple)
                            highest_cost = paired_costs[-1][3]

            for j in range(len(cand)):
                rule1 = cand[j]
                for k in range(j + 1, len(cand)):
                    rule2 = cand[k]
                    for l in range(k + 1, len(cand)):
                        rule3 = cand[l]
                        c_var_name = 'c_' + str(i) + ',(' + str(j) + ',' + str(k) + ',' + str(l) + ')'

                        try:
                            cand_state = env.apply_block(curr_state, [rule1, rule2, rule3])
                        except RuntimeError:
                            pass
                        else:
                            cost = env.get_state_edit_dist(gold_state, cand_state)
                            new_tuple = (c_var_name, i, [j, k, l], cost)

                            if len(paired_costs) < k_matches or cost < highest_cost:
                                if len(paired_costs) == k_matches:
                                    del paired_costs[-1]
                                bisect.insort_left(paired_costs, new_tuple)
                                highest_cost = paired_costs[-1][3]

            # now that we have the k matchings with the lowest edit distance with this particular gold block, we can add the variables corresponding to these matchings to each of the relevant constraints:
            for var_name, i, cand_rules, cost in paired_costs:
                v[var_name] = solver.IntVar(0, 1, var_name)
                c['gold_' + str(i)].SetCoefficient(v[var_name], 1)
                for rule_index in cand_rules:
                    c['cand_' + str(rule_index)].SetCoefficient(v[var_name], 1)
                c['min_match'].SetCoefficient(v[var_name], 1)
                objective.SetCoefficient(v[var_name], cost)

            # update the state and continue onto the next block in gold
            curr_state = gold_state

    # we now update min_match with bounds based on the number of actually active gold blocks
    min_match_number = int(match_proportion * number_active_gold_blocks)
    c['min_match'].SetBounds(min_match_number, number_active_gold_blocks)

    # solve the ILP
    objective.SetMinimization()
    print("Solving the ILP...")
    solver.Solve()

    # reconstruct the solution and return it
    print('Minimum objective function value = %f' % solver.Objective().Value())
    print('Minimum objective function value per match = %f' % (solver.Objective().Value() / min_match_number))

    # interpret solution as a matching, returning a list pairing indices of blocks in gold to a list of indices of matched rules in cand
    matching = []
    for name, var in v.items():
        if var.solution_value():  # ie if this variable was set to 1
            # print('%s = %d' % (var.name(), var.solution_value()))

            # process the variable name to extract the IDs of the matched rules
            # example name: b_16,(20,24,27)
            id_half = name.split('_')[1]  # name: 16,(20,24,27)
            gold_half, cand_half = id_half.split('(')  # 16, ; 20,24,27)
            gold_var = int(gold_half[:-1])  # remove the comma and turn into an int
            cand_vars = cand_half[:-1].split(',')  # remove the right paren and split on the commas
            cand_vars = [int(x) for x in cand_vars]  # make the numbers into ints

            match = [gold_var, cand_vars]
            matching.append(match)

            if g.interpret_matching:
                gold_id, cand_ids = match
                gold_block = gold[gold_id]
                cand_rules = [cand[j] for j in cand_ids]
                cost = objective.GetCoefficient(v[name])
                print('---')
                print('gold block', gold_id, ':', gold_block)
                print('matched to rules:', cand_rules)
                print('with dist', str(cost))

    return matching


if __name__ == "__main__":
    add_argument("match_proportion", dtype=float, default=.7, msg="Proportion of gold blocks to force matches on")
    add_argument("k_matches", dtype=int, default=10, msg="Number of matches to consider per gold block")
    add_argument("interpret_matching", dtype=bool, default=False, msg="Flag to print out the rule matching")

    manager, gold, states, refs = rule.simulate()
    initial_state = states[0]

    cand = read_rules_from_txt('data/toy_cand_rules.txt')
    # gold = read_rules_from_txt('data/toy_gold_rules.txt')

    # turn gold rules into singleton lists since we expect gold to be in the form of blocks
    # Group rules by refs. Assume refs are chronologically ordered.
    gold_blocks = list()
    ref_set = set()  # This stores every ref that has been encountered.
    for gold_rule, ref in zip(gold, refs):
        if ref not in ref_set:
            ref_set.add(ref)
            gold_blocks.append([gold_rule])
        else:
            gold_blocks[-1].append(gold_rule)

    env = manager.env

    matching = match_rulesets(gold_blocks, cand, env, g.match_proportion, g.k_matches)
