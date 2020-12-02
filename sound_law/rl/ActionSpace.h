#pragma once

#include <Action.h>
#include <TreeNode.h>
#include <Word.h>
#include <Site.h>

class ActionSpace
{
public:
    static bool use_conditional;

    static void set_conditional(bool);

    ActionSpace();

    vector<Action *> actions;
    unordered_map<abc_t, vector<abc_t>> edges;

    // void register_action(abc_t, abc_t, const vector<abc_t> &, const vector<abc_t> &);
    void register_edge(abc_t, abc_t);

    Action *get_action(action_t);
    void set_action_allowed(TreeNode *);
    size_t size();
    void clear_cache();
    size_t get_cache_size();
    vector<abc_t> expand_a2i();

private:
    void register_node(SiteNode *);

    unordered_map<WordKey, Word *> word_cache;
    unordered_map<Site, vector<action_t>> site_map;
    mutex mtx;
    mutex site_mtx;

    vector<abc_t> a2i_cache;
};