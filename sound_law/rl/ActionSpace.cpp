#include <ActionSpace.h>

bool ActionSpace::use_conditional = false;

void ActionSpace::set_conditional(bool conditional)
{
    ActionSpace::use_conditional = conditional;
}

ActionSpace::ActionSpace()
{
    this->actions = vector<Action *>();
    this->word_cache = unordered_map<string, Word *>();
    this->uni_map = unordered_map<long, vector<long>>();
}

void ActionSpace::register_action(long before_id, long after_id)
{
    long action_id = this->actions.size();
    Action *action = new Action(action_id, before_id, after_id);
    this->actions.push_back(action);
    if (this->uni_map.find(before_id) == this->uni_map.end())
    {
        this->uni_map[before_id] = vector<long>();
    }
    this->uni_map[before_id].push_back(action_id);
}

void ActionSpace::register_action(long before_id, long after_id, long pre_id)
{
    long action_id = this->actions.size();
    Action *action = new Action(action_id, before_id, after_id, pre_id);
    this->actions.push_back(action);
    if (this->pre_map.find(before_id) == this->pre_map.end())
        this->pre_map[before_id] = unordered_map<long, vector<long>>();
    unordered_map<long, vector<long>> &nested = this->pre_map[before_id];
    if (nested.find(pre_id) == nested.end())
        nested[pre_id] = vector<long>();
    nested[pre_id].push_back(action_id);
}

Action *ActionSpace::get_action(long action_id)
{
    return this->actions[action_id];
}

vector<long> ActionSpace::get_action_allowed(const VocabIdSeq &vocab_i)
{
    unordered_set<long> action_set_uncond = unordered_set<long>();
    unordered_map<long, unordered_set<long>> pre_keys = unordered_map<long, unordered_set<long>>();
    for (long i = 0; i < vocab_i.size(); ++i)
    {
        string key = get_key(vocab_i[i]);
        unique_lock<mutex> lock(this->mtx);
        if (this->word_cache.find(key) == this->word_cache.end())
        {
            Word *new_word = new Word(vocab_i[i]);
            this->word_cache[new_word->key] = new_word;
            // Deal with unconditional changes.
            unordered_set<long> &new_aa_uncond = new_word->action_allowed_uncond;
            for (auto const uni_key : new_word->uni_keys)
            {
                vector<long> &map_values = this->uni_map[uni_key];
                new_aa_uncond.insert(map_values.begin(), map_values.end());
            }
        }
        Word *word = this->word_cache[key];
        lock.unlock();
        unordered_set<long> &aa_uncond = word->action_allowed_uncond;
        action_set_uncond.insert(aa_uncond.begin(), aa_uncond.end());
        // Deal with prefixed conditional changes. The actual set of actions is not unknown until all words (their pre_keys) are aggregated.
        for (auto const &item : word->pre_keys)
        {
            long c_key = item.first;
            const unordered_set<long> &p_keys = item.second;
            if (pre_keys.find(c_key) == pre_keys.end())
                pre_keys[c_key] = unordered_set<long>();
            pre_keys[c_key].insert(p_keys.begin(), p_keys.end());
        }
    }
    vector<long> ret = vector<long>(action_set_uncond.begin(), action_set_uncond.end());
    for (auto const &item : pre_keys)
    {
        const unordered_set<long> &p_keys = item.second;
        if (p_keys.size() > 1)
        {
            long c_key = item.first;
            unordered_map<long, vector<long>> &c_values = this->pre_map[c_key];
            for (long value : p_keys)
            {
                vector<long> &p_values = c_values[value];
                ret.insert(ret.end(), p_values.begin(), p_values.end());
            }
        }
    }
    return ret;
}

long ActionSpace::size()
{
    return this->actions.size();
}

void ActionSpace::clear_cache()
{
    for (auto const &item : this->word_cache)
    {
        delete item.second;
    }
    this->word_cache.clear();
}

long ActionSpace::get_cache_size()
{
    return this->word_cache.size();
}