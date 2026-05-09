# agents/critic.py

def critic_agent(state):
    confidence = state["confidence"]
    iterations = state.get("iterations", 0)

    if confidence < 0.8 and iterations < 2:
        return {
            "action": "retry",
            "iterations": iterations + 1
        }

    return {
        "action": "accept",
        "iterations": iterations
    }