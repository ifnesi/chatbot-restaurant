import os
import requests

from dotenv import load_dotenv, find_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models

from utils import (
    md5_hash,
    sys_exc,
)


DOCUMENTS_SINGLE = [
    # animals
    "Tiger",
    "Elephant",
    "Dolphin",
    "Eagle",
    "Kangaroo",
    "Lion",
    "Panda",
    "Zebra",
    "Penguin",
    "Giraffe",
    # colors
    "Red",
    "Blue",
    "Green",
    "Yellow",
    "Orange",
    "Black",
    "White",
    "Purple",
    "Pink",
    "Brown",
    # car_manufacturers
    "Toyota",
    "Ford",
    "BMW",
    "Mercedes",
    "Honda",
    "Chevrolet",
    "Audi",
    "Nissan",
    "Hyundai",
    "Volkswagen",
    # electronic_items
    "Smartphone",
    "Laptop",
    "Tablet",
    "Camera",
    "Television",
    "Headphones",
    "Smartwatch",
    "Gaming Console",
    "Drone",
    "E-Reader",
    # clothing_items
    "Jacket",
    "Hat",
    "T-shirt",
    "Jeans",
    "Shorts",
    "Sweater",
    "Coat",
    "Scarf",
    "Hoodie",
    "Socks",
    # countries
    "Japan",
    "USA",
    "Germany",
    "Brazil",
    "Australia",
    "Canada",
    "China",
    "South Africa",
    "South Korea",
    "Kenya",
]

DOCUMENTS_SENTENCE = [
    # animals
    "The tiger prowls silently through the jungle.",
    "An elephant trumpeted loudly near the river.",
    "A dolphin gracefully leapt out of water.",
    "The eagle soared high above the mountains.",
    "A kangaroo hopped quickly across the plains.",
    "The lion roared loudly in the savannah.",
    "Panda cubs play happily in the bamboo.",
    "A zebra grazed peacefully on the grasslands.",
    "Penguin waddled adorably across the icy shore.",
    "A giraffe nibbled leaves from tall trees.",
    # colors
    "Red roses bloomed brightly in the garden.",
    "Blue waves crashed gently on the shore.",
    "A green forest stretched to the horizon.",
    "Yellow sunflowers swayed in the summer breeze.",
    "The orange sunset painted the evening sky.",
    "A black cat darted across the street.",
    "White snow covered the ground completely today.",
    "Purple lavender fields filled the fresh air.",
    "Pink cherry blossoms adorned the spring trees.",
    "Brown soil nurtured the plants to grow.",
    # car_manufacturers
    "Toyota cars are known for their reliability.",
    "A sleek Ford parked outside the house.",
    "BMW's engines are built for smooth performance.",
    "Mercedes cars epitomize luxury and top comfort.",
    "Honda produces efficient vehicles loved by many.",
    "A Chevrolet truck rumbled down the dusty road.",
    "Audi drivers enjoy powerful yet elegant designs.",
    "Nissan offers reliable cars for everyday use.",
    "Hyundai's lineup includes affordable and stylish models.",
    "Volkswagen has a rich history of engineering excellence.",
    # electronic_items
    "A smartphone buzzed with new incoming messages.",
    "Laptop screens illuminated the late-night study session.",
    "The tablet displayed the latest digital artwork.",
    "A high-resolution camera captured the stunning scenery.",
    "A large television broadcasted the exciting soccer game.",
    "Headphones delivered crisp music to listeners' ears.",
    "The smartwatch tracked steps and monitored health.",
    "A gaming console provided entertainment for the kids.",
    "The drone soared and captured aerial footage.",
    "An e-reader displayed thousands of books digitally.",
    # clothing_items
    "A warm jacket kept out the cold.",
    "The hat shielded the face from sun.",
    "A comfortable T-shirt is great for summer.",
    "Jeans are perfect for a casual outing.",
    "Shorts are ideal for the beach weather.",
    "A soft sweater feels cozy on chilly evenings.",
    "The coat hung neatly on the rack.",
    "A wool scarf wrapped around the neck snugly.",
    "A hoodie provided comfort on the windy day.",
    "Colorful socks peeked out from the shoes.",
    # countries
    "Japan is famous for its cherry blossoms.",
    "The USA hosts many diverse cultural experiences.",
    "Germany is known for its precision engineering.",
    "Brazil has lively festivals and beautiful beaches.",
    "Australia is home to diverse wildlife species.",
    "Canada boasts breathtaking natural landscapes and lakes.",
    "China has a rich and ancient history.",
    "South Africa is known for stunning safaris.",
    "South Korea is famous for its technology.",
    "Kenya has beautiful savannahs and incredible wildlife.",
]

if __name__ == "__main__":
    # Load env variables
    load_dotenv(find_dotenv())
    env_vars = dict(os.environ)

    REST_API_ENDPOINT = f"http://localhost:{env_vars.get('EMBEDDING_PORT')}"
    REST_API_ENDPOINT_URL = f"{REST_API_ENDPOINT}{env_vars.get('EMBEDDING_PATH')}"
    VDB_COLLECTION = "Test_Semantics_"

    # Qdrant (Vector-DB)
    VDB_CLIENT = QdrantClient(
        host="qdrant",
        port=6333,
    )

    collection_created = [False, False]

    for doc in zip(DOCUMENTS_SINGLE, DOCUMENTS_SENTENCE):
        for n, d in enumerate(doc):
            # Generate vector Data
            response = requests.post(
                REST_API_ENDPOINT_URL,
                headers={
                    "Content-Type": "text/plain; charset=UTF-8",
                },
                data=d,
            )
            vector_data = response.json().get("vector_data", list())

            id = md5_hash(d)
            print(f"ID......: {id}")
            print(f"Document: {d}")
            print(f"Vector..: {vector_data}")

            # Create collection
            if not collection_created[n]:
                collection_created[n] = True
                VDB_CLIENT.create_collection(
                    collection_name=f"{VDB_COLLECTION}_{n}",
                    vectors_config=models.VectorParams(
                        size=len(vector_data),
                        distance=models.Distance.COSINE,
                    ),
                )

            # Upsert collection
            VDB_CLIENT.upsert(
                collection_name=f"{VDB_COLLECTION}_{n}",
                points=[
                    models.PointStruct(
                        id=id,
                        vector=vector_data,
                        payload={
                            "doc": d,
                        },
                    ),
                ],
            )
