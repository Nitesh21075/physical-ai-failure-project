# Project Brief

## One-line idea

Build an automated red-team/research harness for physical AI that searches for rare environmental failures and collects the trajectories needed to evaluate and improve world models and robot systems.

## Problem

World models can struggle with rare and out-of-distribution physical events. Unfortunately, the real-world data needed to learn these events is often the hardest data to collect.

Examples include:
- mine roof/structural collapse
- fire ignition or spread
- falling beams/debris
- secondary structural failure
- hazardous events triggered by robot actions

These events can have high human, robotic, financial, and safety penalties, so deliberately collecting them in reality is often unacceptable.

## What “failure” means here

The target failure is primarily an **environmental failure/consequence**, not merely a robot task failure.

Examples:

`robot action -> destabilizes support -> roof collapse`

`robot action -> object/equipment interaction -> fire starts`

`robot action -> disturbed structure -> falling debris`

A robot may even successfully execute its intended action while causing a catastrophic environmental consequence. That consequence is the failure of interest.

## Solution

Build an automated research harness that:

1. defines a scenario and robot task;
2. runs the robot/controller in an environment;
3. records observations, actions, and environment state;
4. evaluates both robot/task outcomes and environmental consequences;
5. stores the trajectory and failure metadata;
6. uses experiment history to select or generate subsequent experiments;
7. can run the same research loop against different environment backends.

The first backend is expected to be Isaac Sim/PhysX on an AWS GPU workstation. A neural world model backend is intended to follow when the available API supports the required interaction model.

## Benefit

The resulting dataset can contain rare physical failure trajectories and paired neural/physics outcomes. It can be used to:

- evaluate world models on rare physical events;
- identify where neural world models disagree with physics-grounded simulation;
- investigate whether additional data can improve world-model behavior on those events;
- create difficult evaluation/training scenarios for physical-AI and robot policies.

The project should avoid claiming that the hackathon proves world-model fine-tuning improves physics accuracy unless such an experiment is actually completed.

## Hackathon framing

The strongest product/research framing is:

**“Automated red-teaming for physical AI: find the environmental failures robots cannot safely experience in the real world.”**

The world model should be substantive, not decorative. If the available model is only a video generator, do not pretend it is a structured robot simulator. Use it for visual counterfactual generation/augmentation or build the neural-world backend only when its actual API supports closed-loop interaction.
