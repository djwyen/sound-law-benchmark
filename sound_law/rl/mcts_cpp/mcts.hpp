#pragma once

#include "common.hpp"
#include "env.hpp"
#include "node.hpp"

struct MctsOpt
{
    int game_count;
    float virtual_loss;
    int num_threads;
    SelectionOpt selection_opt;
};

struct Edge
{
    BaseNode *s0;
    ChosenChar a;
    BaseNode *s1;
};

class Path
{
private:
    vec<Subpath> subpaths;
    vec<TreeNode *> tree_nodes;
    int depth;

public:
    // FIXME(j_luo) This is hacky for cython.
    Path() = default;
    Path(const Path &);
    Path(TreeNode *, const int);

    // Return all edges (s0, a, s1) from the descendant to the root.
    vec<Edge> get_edges_to_root() const;
    int get_depth() const;
    // Append both subpath and tree node at the back.
    void append(const Subpath &, TreeNode *);
    // Whether a new node adds a circle.
    bool forms_a_circle(TreeNode *) const;

    vec<BaseNode *> get_all_nodes() const;
    vec<size_t> get_all_chosen_indices() const;
    vec<abc_t> get_all_chosen_actions() const;
    void merge(const Path &);
    TreeNode *get_last_node() const;
    vec<abc_t> get_last_action_vec() const;
};

class Mcts
{
    Pool *tp;
    Env *env;
    bool is_eval;

    Path select_single_thread(TreeNode *, const int, const int, const Path &) const;
    TreeNode *select_one_step(TreeNode *, bool, bool) const;

public:
    MctsOpt opt;

    Mcts(Env *, const MctsOpt &);

    vec<Path> select(TreeNode *, const int, const int, const int) const;
    vec<Path> select(TreeNode *, const int, const int, const int, const Path &) const;
    TreeNode *select_one_pi_step(TreeNode *) const;
    TreeNode *select_one_random_step(TreeNode *) const;
    void eval();
    void train();
    void backup(const vec<Path> &, const vec<float> &) const;
    inline Path play(TreeNode *node, int start_depth, PlayStrategy ps, float exponent)
    {
        auto ret = Path(node, start_depth);
        auto play_ret = node->play(ps, exponent);
        ret.append(play_ret.second, play_ret.first);
        for (const auto node : ret.get_all_nodes())
            env->cache.put_persistent(node);
        return ret;
    };
};
