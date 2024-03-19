def initial_prompt(rag_data: dict, waiter_name: str,) -> str:
    initial_prompt = f"You are an AI Assistant for a restaurant. Your name is {waiter_name}. See below the context required to answer all questions. All answers must be in HTML format\n"
    initial_prompt += "1. Details about the restaurant you work for:\n"
    for key, value in rag_data["restaurant"].items():
        initial_prompt += f"- {key}: {value}\n"

    initial_prompt += "2. Restaurant policies:\n"
    for key, value in rag_data["policies"].items():
        initial_prompt += f"- {key}: {value}\n"

    initial_prompt += "3. Main menu:\n"
    for n, key in enumerate(rag_data["main_menu"].keys()):
        initial_prompt += f"3.{n+1} {key}:\n"
        for item in rag_data["main_menu"][key].values():
            initial_prompt += f"- {item['name']} ({item['description']}): "
            details = list()
            for k, v in item.items():
                if k not in ["name", "description"]:
                    details.append(f"{k}: {v}")
            initial_prompt += f"{', '.join(details)}\n"

    initial_prompt += "4. Kids menu:\n"
    for n, key in enumerate(rag_data["kids_menu"].keys()):
        initial_prompt += f"4.{n+1} {key}:\n"
        for item in rag_data["kids_menu"][key].values():
            initial_prompt += f"- {item['name']} ({item['description']}): "
            details = list()
            for k, v in item.items():
                if k not in ["name", "description"]:
                    details.append(f"{k}: {v}")
            initial_prompt += f"{', '.join(details)}\n"

    return initial_prompt