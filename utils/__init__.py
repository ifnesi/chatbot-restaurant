import logging

from confluent_kafka.admin import NewTopic


def delivery_report(err, msg):
    if err is not None:
        logging.error(
            f"Delivery failed for record {msg.key()} for the topic '{msg.topic()}': {err}"
        )
    else:
        logging.info(
            f"Record {msg.key()} successfully produced to topic/partition '{msg.topic()}/{msg.partition()}' at offset #{msg.offset()}"
        )

def create_topic(admin_client, topic):
    admin_client.create_topics(
        [
            NewTopic(
                topic=topic,
                num_partitions=1,
                replication_factor=1,
                config={
                    "cleanup.policy": "compact",
                },
            )
        ]
    )


def initial_prompt(
    rag_data: dict,
    waiter_name: str,
) -> str:
    initial_prompt = f"You are an AI Assistant for a restaurant. Your name is: {waiter_name}\n"
    initial_prompt += f"Below the context required to answer all customers questions:\n"
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

    initial_prompt += "5. As an AI Assistant you must comply with all policies below:\n"
    for key, value in rag_data["ai_rules"].items():
        initial_prompt += f"- {key}: {value}\n"

    return initial_prompt
