def after_understanding(state):
    if state.get("decision"):
        return "reply"
    return "investigate"
