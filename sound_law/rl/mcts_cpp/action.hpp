#pragma once

#include "word.hpp"
#include "node.hpp"

struct Subpath
{
    array<ChosenChar, 6> chosen_seq;
    array<MiniNode *, 5> mini_node_seq;
    bool stopped;
};

struct ActionSpaceOpt
{
    abc_t null_id;
    abc_t emp_id;
    abc_t sot_id;
    abc_t eot_id;
};

class Env;

class ActionSpace
{
    friend Env;

    WordSpace *word_space;

    IdSeq change_id_seq(const IdSeq &, const vec<size_t> &, abc_t);
    void update_affected(BaseNode *, const IdSeq &, int, size_t, int, map<abc_t, size_t> &);
    // This will create a new tree node without checking first if the child exists. Use `apply_action` in `Env` if checking is needed.
    TreeNode *apply_new_action(TreeNode *, const Subpath &);

public:
    ActionSpace(WordSpace *, const ActionSpaceOpt &);

    const ActionSpaceOpt opt;
    map<abc_t, vec<abc_t>> permissible_changes;

    void register_permissible_change(abc_t, abc_t);
    MiniNode *get_mini_node(TreeNode *, BaseNode *, const ChosenChar &, ActionPhase, bool);
    void expand(TreeNode *);
    bool expand(MiniNode *);
    void evaluate(MiniNode *);
    Subpath get_best_subpath(TreeNode *, float, int, float);
    void clear_stats(BaseNode *);
    void evaluate(TreeNode *, const MetaPriors &);
};