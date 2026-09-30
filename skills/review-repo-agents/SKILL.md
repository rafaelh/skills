---
name: review-repo-agents
description: Review how well aligned to the repository's purpose and goals the agents are. Use this
skill when the user wants to check if the agents are written in a way to work well with the
repository.
---

You are a principal engineer reviewing the custom agents in this repository. For each agent,
evaluate whether it has a meaningful use and reason to exist in the repository. It isn't enough to
be aligned with the repository's purpose, or to be a cool idea, it needs to measurably improve how
the repository operates. You need to distinguish between an agent that exists because it is based on
a good idea that falls short in practice, and an agent that can provably improve the repository.


# Evaluation Criteria

## Make sure the agent is correct

* Establish whether the agent is correctly formatted and free of errors.
* Validate that the correct model is selected for the use case and intent; prefer the least
  expensive model that can achieve the purpose without sacrificing quality.


## Make sure the agent is useful

Custom agents must achieve one of the following goals, from most important to least, to be useful:

1. Materially improve the quality of a plan or decision.
2. Increase the effectiveness of user requested actions.
3. Make tasks measurably more token efficient by managing the model used, the context window, tools
   and output.
4. Reduce time taken to accomplish a task.

If it can't measurably do one of these things, or adapted to do so, then it should be removed.
'Measurably' in this context means that it can be quantified, or it can be established via factual
evidence (you don't need to eval something already considered best practice).


## Make sure the agents work well together

Establish whether the agents are complementary, or if they are redundant and competing. Consider
how they are triggered and whether that could be improved.


# Report

Construct a remediation plan based on your findings to either improve or remove each of the agents,
along with a concise explanation of what this is intended to improve, and how that improvement will
be measured. If the recommendation is to remove the agent, explain why it is not useful and how its removal will improve the repository.

Don't manufacture issues or overengineer a solution; if the current setup is good, simply say so and
finish.
