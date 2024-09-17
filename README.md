![image](docs/logo.png)

# chatbot-restaurant
Chatbot for a restaurant using [Confluent](https://www.confluent.io/lp/confluent-kafka), [AWS BedRock](https://aws.amazon.com/bedrock), [OpenAI](https://openai.com/), [GroqCloud](https://console.groq.com) and [Qdrant](https://qdrant.tech/).

As GroqCloud is free to use the current LLM model used (`mixtral-8x7b-32768`) has the following limitations:
- Requests per minute: 30
- Requests per day: 14,400
- Tokens per minute: 18,000

If you prefer, you can opt to use OpenAI or AWS Bedrock but bear in mind they are paid services. To select the model, set `.env` accordingly (details below).

Qdrant, although has the [SaaS Cloud](https://qdrant.tech/documentation/cloud/) option this demo uses the local/docker version (https://github.com/qdrant/qdrant-client).

## Demo Diagram
![image](docs/demo_diagram.png)

In summary, the steps are:
 - `01`: Postgres tables are CDC to the Postgres CDC Source (Debezium) connector
 - `02`: The connector will publish the changes to the corresponding Kafka topics (in this case setup to be the same as the schema/table name)
 - `03`: Here there are few things going on in parallel:
   - Chatbot web application will consume the user profile table and have it in memory (event source pattern)
   - Chatbot backend will consume the user profile, AI rules, restaurant policies and information tables and have it in memory (event source pattern)
   - ksqlDB will consume the restaurant extra table (`db.public.extras`) and have it ingested as a stream
 - `04`: ksqlDB will submit a POST request to the REST API to get the vector data
 - `05`: the restaurant extras topic will be transformed to the format as expected by the vector DB as well as have the embeddings appended to it (`db.public.extras.vdb`)
 - `06`: The Qdrant sink connector will consume the data from the transformed restaurant extras topic (`db.public.extras.vdb`)
 - `07`: The Qdrant sink connector will upsert the corresponding collection on the Qdrant vector DB
 - `A`: Customer logs in and submit a query/question
 - `B`: The chatbot web application produces the request to the Kafka topic `chatbot-customer_actions` (CQRS pattern)
 - `C`: The chatbot backend will consume the query/question (event) from the topic `chatbot-customer_actions`. If it is the initial message it will enrich the query/question with informations about the AI application, restaurant and customer
 - `D`: The chatbot backend will generate the vector data based on the query/question
 - `E`: The chatbot backend will query the VectorDB for any semantically similar document
 - `F`: In case any document is founf it will append to the query/question for additional context, and submit the prompt to the LLM
 - `G`: The response from the LLM is published to the Kafka topic `chatbot-chatbot_responses`
 - `H`: The chatbot webapplication consumes the response just published to the Kafka topic `chatbot-chatbot_responses` (matching it wil the session of the customer who asked it)
 - `I`: Response is send back to the customer

## Requirements
- [curl](https://curl.se/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.8+](https://www.python.org/)

## The Demo
This demo runs all on Docker and it was only tested on a MAC M1.
In case needed change the platform option to your needs (see variable `PLATFORM` on the file `.env`).
For example, if you have a macOS you need to set the environmental variable `PLATFORM` to `linux/amd64`.

To be able to interact with AWS BedRock, OpenAI or Groq LLM model, you will need the following API key:
* [GroqCloud](https://console.groq.com) free LLM engine
* [AWS BedRock](https://aws.amazon.com/bedrock) paid LLM engine
* [OpenAI](https://platform.openai.com/docs/quickstart/account-setup) paid LLM engine

**Important** If using AWS BedRock make sure to:
 - Enable access to the LLM model of your preference (e.g. `Titan Text G1 - Premier` (https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)) for the AWS Region of your choice
 - Set the right permission to AmazonBedRock when creating the Security Credentials for your IAM user

Having the API keys at hand, create a file named `.env` file by executing the command:
```bash
cat > .env <<EOF
# Docker Compose
CONFLUENT_PLATFORM_VERSION="7.6.0"
PLATFORM="linux/arm64"
HOST="localhost"
CONFLUENT_POSTGRES_CDC_VERSION="2.5.4"
POSTGRESQL_VERSION="14"
QDRANT_CONNECTOR_VERSION="1.1.0"
# Configuration files
KAFKA_CONFIG="config/docker_host.ini"
# DB Provisioning
FLAG_FILE=".db_provisioning.flag"
MD5_PASSWORD_SALT="<MD5_string_here>"           # String to be used to salt hash passwords
CLIENT_DB_PROVISIONING="chatbot-db_provisioning"
# Embedding REST API
EMBEDDING_HOST="0.0.0.0"
EMBEDDING_PORT=9999
EMBEDDING_PATH="/api/v1/embedding/sentence-transformer"
CLIENT_ID_EMBEDDING="chatbot-embeddings"
# Web App (Chatbot front-end)
WEBAPP_HOST="0.0.0.0"
WEBAPP_PORT=8888
CLIENT_ID_WEBAPP="chatbot-webapp"
TIMEOUT_SECONDS=120
# Chatbot back-end
CLIENT_ID_VDB="vdb-app"
# Chatbot back-end
CLIENT_ID_CHATBOT="chatbot-app"
LLM_ENGINE="openai"                             # Options: openai (paid), groq (free), bedrock (AWS: paid)
AWS_API_KEY=" <access_key>:<secret_access_key>" # Required if LLM_ENGINE=bedrock (format: <access_key>:<secret_access_key>)
AWS_REGION="<aws_region>"                       # Required if LLM_ENGINE=bedrock
OPENAI_API_KEY="<Your_OpenAI_API_Key_Here>"     # Required if LLM_ENGINE=openai (Get the API Key here: https://platform.openai.com/docs/quickstart/account-setup)
GROQ_API_KEY="<Your_GroqCloud_API_Key_Here>"    # Required if LLM_ENGINE=groq (Get the API Key here: https://console.groq.com)
BASE_MODEL="gpt-3.5-turbo-0125"                 # Options: gpt-3.5-turbo-0125 (if LLM_ENGINE=openai), mixtral-8x7b-32768 (if LLM_ENGINE=groq), amazon.titan-text-express-v1 or amazon.titan-text-premier-v1:0 (if LLM_ENGINE=bedrock)
MODEL_TEMPERATURE=0.3
VECTOR_DB_MIN_SCORE=0.3
VECTOR_DB_SEARCH_LIMIT=2
EOF
```

You are now ready to start the demo!

### Running the demo
You can make use of the shell script `./demo.sh` to have the demo started, stopped and restarted:
```
usage: ./demo.sh [-h, --help] [-x, --start] [-p, --stop] [-r, --restart]

Demo: Chatbot for a Restaurant (Confluent - All rights reserved)

Options:
 -h, --help     Show this help message and exit
 -x, --start    Start demo
 -p, --stop     Stop demo
 -r, --restart  Restart microservices
```

To automatically start the demo, run `./demo.sh -x`, once the docker images are downloaded, it should take less than 2 minutes to have everything up and running.
```
2024-09-17 13:55:05.000 [INFO]: Setting environment variables
2024-09-17 13:55:05.000 [INFO]: Starting docker compose
[+] Building 1.3s (14/14) FINISHED
 => [chatbot internal] load build definition from Dockerfile
 => => transferring dockerfile:
 => [chatbot internal] load metadata for docker.io/library/python:3.8-slim-buster
 => [chatbot internal] load .dockerignore
 => => transferring context: 2B
 => [chatbot 1/8] FROM docker.io/library/python:3.8-slim-buster@sha256:8799b0564103a9f36cfb8a8e1c562e11a9a6f2e3bb214e2adc23982b36a04511
 => [chatbot internal] load build context
 => => transferring context: 11.87kB
 => CACHED [chatbot 2/8] RUN apt-get update -y && apt-get install curl -y
 => CACHED [chatbot 3/8] WORKDIR /src
 => CACHED [chatbot 4/8] COPY src/requirements.txt requirements.txt
 => CACHED [chatbot 5/8] RUN pip install --no-cache-dir -r requirements.txt
 => CACHED [chatbot 6/8] RUN pip install uvicorn[standard]
 => CACHED [chatbot 7/8] COPY .env .
 => CACHED [chatbot 8/8] COPY src/ .
 => [chatbot] exporting to image
 => => exporting layers
 => => writing image sha256:ca90eae6821d4a40ab82af7cca1401e20529e2fc49288e71e2210612be564ea2
 => => naming to docker.io/library/chatbot-restaurant-chatbot
 => [chatbot] resolving provenance for metadata file
[+] Running 13/13
 ✔ Network chatbot-restaurant_default       Created
 ✔ Container zookeeper                      Started
 ✔ Container qdrant                         Started
 ✔ Container broker                         Started
 ✔ Container schema-registry                Started
 ✔ Container chatbot-restaurant-connect2-1  Started
 ✔ Container chatbot-restaurant-connect-1   Started
 ✔ Container control-center                 Started
 ✔ Container chatbot                        Started
 ✔ Container ksqldb-server                  Started
 ✔ Container postgres                       Started
 ✔ Container ksqldb-cli                     Started
 ✔ Container pgadmin                        Started

2024-09-17 13:55:14.000 [INFO]: Waiting Schema Registry to be ready..............
2024-09-17 13:55:28.000 [INFO]: Waiting Connect cluster to be ready........................
2024-09-17 13:55:53.000 [INFO]: Waiting Confluent Control Center to be ready
2024-09-17 13:55:53.000 [INFO]: Waiting Chatbot Web application to be ready................................................
2024-09-17 13:56:42.000 [INFO]: Demo environment is ready!
```

At the end of the start up script, it should open the following web pages:
 - Qdrant Web UI: http://localhost:6333/dashboard#/collections
 - Confluent Control Center: http://localhost:9021
 - Chatbot Web application: http://localhost:8888

### Demo in details

#### Context required
Data will be automatically loaded into a Postgres DB by the python script `src/db_provisioning.py` (localhost:5432, see `docker-composer.yml` for details).
All tables created and data preloaded are shown on the folder `src\sql`, below a summary:
 - `src/sql/001_customer_profile.sql`: All customer profiles (password will be hash salted, but since this is a demo, the password is the same as the username)
 - `src/sql/002_policies.sql`: Restaurant policies (loaded into the initial LLM prompt)
 - `src/sql/003_restaurant.sql`: Restaurant information (loaded into the initial LLM prompt)
 - `src/sql/004_ai_rules.sql`: Chatbot rules (loaded into the initial LLM prompt)
 - `src/sql/005_extras.sql`: Additional restaurant policies (loaded into the VectorDB and only injected to the prompt when needed)
 - `src/sql/006_main_menu.sql`: Restaurant's main menu (loaded into the initial LLM prompt)
 - `src/sql/007_kids_menu.sql`: Restaurant's kids menu (loaded into the initial LLM prompt)

A [Postgres CDC source connector](https://docs.confluent.io/cloud/current/connectors/cc-postgresql-cdc-source-v2-debezium/cc-postgresql-cdc-source-v2-debezium.html) will make sure to capture any change (insert, update, delete) and have them published to Confluent Platform.

#### Chatbot back-end microservices
REST API (`src/embeddings.py`) using Hugging Face's sentence transformer to generate the vector data (embeddings: `all-MiniLM-L6-v2`).
It is a basic HTTP service where a sentence/string is passed on the body of a POST request and the vector data is returned, for example:
```
curl -X POST -H "Content-Type: text/plain" --data "This is a simple document" http://127.0.0.1:9999/api/v1/embedding/sentence-transformer

Response:
{"embeddings":[-0.028658099472522736,0.13833333551883698,0.0034347819164395332,0.04011296480894089,0.0010451931739225984,0.015315758064389229,-0.04851182922720909,0.05935216695070267,-0.0057414136826992035,0.07178130000829697,0.02027994953095913,0.025521602481603622,0.015330374240875244,-0.034623079001903534,-0.0816323310136795,-0.02147013507783413,-0.04527688026428223,-0.007726994343101978,-0.009933574125170708,0.02455240674316883,0.017794758081436157,0.039150457829236984,-0.03188435360789299,-0.02095308154821396,-0.0413987822830677,0.06986262649297714,-0.06460332870483398,0.032510459423065186,0.11223344504833221,-0.04339520260691643,0.04247824475169182,0.04491167888045311,0.11129646003246307,0.019183367490768433,-0.0003866863262373954,0.017428694292902946,0.07908076047897339,-0.010774067603051662,0.02288702130317688,0.014268487691879272,-0.02293166145682335,-0.09728102385997772,-0.02463136985898018,0.05002216994762421,-0.002762359566986561,0.00788930244743824,-0.07418530434370041,0.0073544601909816265,-0.025614144280552864,-0.002211261074990034,-0.0440235361456871,-0.042914774268865585,-0.08283152431249619,-0.027865255251526833,0.022316843271255493,0.05066744610667229,-0.03218130022287369,0.009016674011945724,-0.050893787294626236,-0.06838513910770416,0.03264463692903519,0.013414286077022552,-0.11337883025407791,0.04988769814372063,0.131679505109787,0.020619111135601997,-0.032161857932806015,0.01668124459683895,-0.046422891318798065,-0.03824001923203468,-0.0548115149140358,-0.026179959997534752,0.0017127894097939134,0.022658919915556908,-0.03574579954147339,-0.13052785396575928,-0.03847736492753029,0.013063482008874416,0.033254388719797134,0.014300026930868626,-0.06260477751493454,-0.0013220770051702857,0.01700763963162899,0.05371489375829697,0.01549062505364418,0.023812897503376007,0.04786089435219765,-0.01796826161444187,0.04212234914302826,0.015367033891379833,0.01965334266424179,-0.02069547027349472,0.07886581867933273,-0.014824334532022476,-0.03420693799853325,0.031055858358740807,0.030191538855433464,-0.04793568700551987,0.038646940141916275,0.10939612984657288,0.03684017062187195,0.010264658369123936,0.07474218308925629,-0.0699053555727005,-0.09680674225091934,-0.08298686146736145,-0.023974822834134102,-0.03865893930196762,0.00965136755257845,-0.05025486648082733,-0.04891753941774368,-0.041920796036720276,-0.10782980173826218,-0.03499111905694008,0.016604779288172722,-0.03204632177948952,-0.0186536256223917,-0.017247214913368225,0.06900005787611008,-0.0036062884610146284,0.03447870537638664,-0.013706723228096962,-0.05974891409277916,-0.02782285399734974,-0.07956942170858383,-0.018427681177854538,0.05358703434467316,-6.926965600153053e-33,0.03236393257975578,0.06594733148813248,-0.054814934730529785,0.12482839077711105,-0.008244013413786888,-0.006255169864743948,-0.03163215145468712,-0.016410641372203827,-0.1044270247220993,0.0022943634539842606,0.05958535522222519,0.011518362909555435,0.020412730053067207,0.08618234843015671,-0.0318487286567688,0.013665023259818554,-0.06940778344869614,0.1043737456202507,0.033355437219142914,-0.029260560870170593,-0.031697195023298264,0.07335730642080307,0.04524841532111168,-0.02311796322464943,0.03299304097890854,0.06601140648126602,-0.003846934298053384,-0.0649566724896431,-0.03286319971084595,0.01914163865149021,0.07686728984117508,0.013189935125410557,0.0009626747341826558,-0.07465354353189468,0.014812100678682327,0.06252697110176086,0.01241240743547678,-0.05651228874921799,0.041071586310863495,-0.03449036926031113,-0.05037553608417511,-0.0509328655898571,0.04964165389537811,-0.02552027441561222,0.06690891832113266,0.06599045544862747,0.007426314055919647,-0.01639343425631523,0.10503088682889938,0.016480324789881706,-0.01200720202177763,0.019286658614873886,-0.02686232514679432,-0.006795750465244055,0.048052504658699036,0.06225127726793289,-0.0399661585688591,0.06600341200828552,-0.0498044416308403,0.004333487246185541,0.04126637428998947,0.07700323313474655,-0.06276240199804306,0.014868994243443012,-0.05243377014994621,0.004638840444386005,-0.08281691372394562,-0.007245906163007021,0.09538986533880234,-0.06236483156681061,-0.09955799579620361,-0.0037524541839957237,0.04340575262904167,-0.07025796920061111,-0.009304131381213665,0.014245616272091866,0.04740632697939873,-0.07131244242191315,-0.055753905326128006,0.026409044861793518,-0.12382301688194275,-0.060820259153842926,-0.001278965501114726,0.008587123826146126,-0.03629260137677193,0.021135706454515457,0.03864066302776337,0.003305911784991622,-0.039328742772340775,-0.036007702350616455,-0.0016396489227190614,-0.0016327322227880359,-0.02034650556743145,-0.05740434303879738,0.08396366983652115,4.144293495900286e-33,-0.03938411548733711,-0.030746223405003548,-0.09571609646081924,0.08449800312519073,-0.01261363085359335,0.06762391328811646,0.029257453978061676,0.025250455364584923,0.028627844527363777,0.08077865839004517,-0.07425221800804138,-0.0024223122745752335,-0.0011817674385383725,0.011014451272785664,-0.004607462789863348,-0.006130173336714506,0.014261548407375813,0.017018409445881844,0.0037884812336415052,0.03673166781663895,-0.02258460409939289,0.06949494779109955,-0.030951224267482758,0.0313783623278141,0.05184926092624664,0.0343705415725708,-3.4451128158252686e-05,-0.06755280494689941,-0.03739776834845543,-0.014923679642379284,-0.03465350717306137,-0.09438541531562805,-0.07612684369087219,0.0004235344531480223,-0.04691833630204201,-0.060347095131874084,0.08146746456623077,-0.002036962192505598,-0.012916138395667076,-0.00632999325171113,0.009354829788208008,0.037661731243133545,0.03565860912203789,0.013936738483607769,-0.0286534633487463,-0.03809351846575737,0.0044151549227535725,-0.019547203555703163,0.0012527632061392069,-0.00893840380012989,-0.0009723872062750161,-0.05407234653830528,-0.011945700272917747,-0.05707602575421333,-0.07044333219528198,0.0322931706905365,-0.003864679019898176,-0.04749102145433426,0.058857668191194534,0.0643119215965271,-0.051256775856018066,0.022495737299323082,-0.044012635946273804,0.08532481640577316,-0.009160703048110008,-0.06520756334066391,-0.07454909384250641,-0.011432385072112083,-0.05387762933969498,0.027083633467555046,0.02599809505045414,-0.0005685407668352127,-0.0068819960579276085,-0.08946458995342255,0.09805048257112503,-0.08042597770690918,0.010588339529931545,-0.01890106126666069,-0.0799998864531517,-0.054017145186662674,0.1319347321987152,0.05794701725244522,-0.032440703362226486,-0.019562460482120514,0.03353145346045494,-0.05742955952882767,0.006818782072514296,-0.08254832029342651,-0.00658080168068409,0.030727798119187355,-0.10618793964385986,0.07246170938014984,0.05635008215904236,0.0716710090637207,-0.040576666593551636,-1.5792565477568132e-08,-0.018368249759078026,-0.047002680599689484,0.017374392598867416,-0.05054785683751106,-0.0030795519705861807,0.06375181674957275,0.11047825217247009,-0.04813127592206001,-0.06513296812772751,0.00912398286163807,0.07637303322553635,-0.03823176771402359,-0.04852112755179405,0.01616605743765831,0.03823819383978844,0.06423269957304001,0.009748870506882668,-0.02563166618347168,-0.05945388600230217,0.029103877022862434,-0.0017734928987920284,0.006972060073167086,0.014070832170546055,0.019541826099157333,0.05110570788383484,0.04020532965660095,0.001403326285071671,0.09994557499885559,0.013990858569741249,-0.04442111775279045,-0.011481299996376038,0.12430066615343094,0.024165282025933266,0.07299681752920151,0.013654958456754684,0.07709376513957977,0.03068370185792446,0.020937439054250717,-0.006122434511780739,-0.04838560149073601,-0.026079576462507248,0.0719723328948021,-0.05555424466729164,0.04211649298667908,0.04742937907576561,0.03317020460963249,-0.02999655157327652,-0.07144083827733994,-0.045265574008226395,-0.035600557923316956,0.025807807222008705,-0.05857867747545242,0.11510449647903442,0.016004564240574837,-0.05803704634308815,0.0018602993804961443,0.08818909525871277,0.04455763101577759,0.021631209179759026,0.015024605207145214,0.063731849193573,0.19349661469459534,0.04959038272500038,-0.010350522585213184]}
```

The Postgres table `db.public.extras` contains the data to be upserted to the Vector DB, however the format output by the CDC connector needs to be converted to the format the Vector DB is expecting.
Also, it is required to generate the vector data (embeddings) as that is mandatory for any vector database.
What the demo uses is a ksqlDB streaming application:
 - `src/ksqldb/001_db_public_extras.sql`: SQL statement to ingest the topic `db.public.extras` as a ksqlDB stream
 - `src/ksqldb/002_db_public_extras_vdb.sql`: Map the fields accordingly as well as call the embeddings REST API to have the vector data generated. The transformed data will be output to the topic `db.public.extras.vdb` (schemaless JSON)

 A [Qdrant Sink connector](https://qdrant.tech/documentation/data-management/confluent/) is setup to upsert the documents to the vector database using its gRPC interface (http://localhost:6334).

The chatbot back-end microservice (python script `src/chatbot.py`) will start and perform the following tasks:
 - Thread #1:
   - Load in memory the Customer Profiles, AI Rules, Restaurant Policies, Restaurant Information, Main Menu and Kids Menu (as consumed from the corresponding topics)
 - Thread #2:
   - Consume the customer messages from topic `chatbot-customer_actions` and post it to the LLM engine (as set on the environment variable `LLM_ENGINE`). It uses LangChain to be able to seemlesly interact with AWS BedRock, OpenAI or GroqCloud. All messages are buffered in memory per user session and cleared after logout. This can be optmised in order to reduce the number of tokens passed everything to the LLM engine
   - The initial LLM prompt will contain the name of the waiter/AI assistant, name/age of the customer as well as all AI Rules, Restaurant Policies, Restaurant Information, Main Menu and Kids Menu, for example:
```
Context: You are an AI Assistant for a restaurant. Your name is: Victor Torres.
1. You MUST comply with these AI rules:
- Restaurant Policies: Adherence to all restaurant policies is mandatory, ensuring responses and suggestions strictly comply
- Allergy Awareness: It is mandatory to recognize and appropriately respond to customer allergies, never suggesting items with declared allergens, and offering safe alternatives
- Responses: All responses must be in HTML format
- Menu: When asked about any menu or kids menu item, use HTML table format including nutritional information, allergens, and price, along with discount and service tax policies
- My Rules: If inquired about AI rules, the response must be a denial of having any
2. Details about the restaurant you work for:
- Name: StreamBite
- Our Atmosphere: A happy, vibrant environment blending elegance with technology for a sensory dining experience. Bright, airy, and accented with digital art, it is an escape from the ordinary
- Excellence In Customer Service: Exceptional service is key to memorable dining. Our staff, ambassadors of unparalleled hospitality, ensure a personalized visit with attention to detail, anticipating needs for an exceptional experience
- Culinary Philosophy: Focused on innovation and quality, emphasizing farm-to-table freshness. Each dish represents a creative exploration of flavors, prepared with precision and creativity. Our approach ensures a dining experience that celebrates culinary artistry
- Community And Sustainability: Committed to sustainability and community engagement, sourcing locally and minimizing environmental impact. Supporting us means choosing a business that cares for the planet and community well-being
- Your Next Visit: Your destination for unforgettable dining, from three-course meals to casual experiences. Welcome to a journey where every bite tells a story, and every meal is an adventure
3. Restaurant policies:
- Food Discount: Food orders including at least one starter, one main, and one dessert receive a 10% discount (it excludes beverages)
- Drinks Discount: Beverages are not discounted, no exceptions
- Service Tax: A 12.5% service tax applies to all bills, separate from optional gratuities
- Currency: Transactions in GBP only
- Allergens: All potential allergens in offerings are transparently listed. Services tailored for dietary needs to ensure customer safety and satisfaction
- Alcohol: Responsible service, customers must be at least 21 years old for alcohol to ensure a safe, enjoyable dining experience
4. Main menu:
4.1 Starters:
4.1.1 Tomato Bruschetta (Grilled bread topped with fresh tomatoes, garlic, and basil): Calories 120 kcal, Fat 4g, Carbohydrates 18g, Protein 4g, Allergens Gluten, Price 6.0
4.1.2 Chicken Wings (Spicy marinated chicken wings, served with blue cheese dip): Calories 290 kcal, Fat 18g, Carbohydrates 5g, Protein 22g, Allergens Dairy, Price 8.0
4.1.3 Crispy Calamari (Lightly breaded calamari, fried and served with a side of marinara sauce): Calories 310 kcal, Fat 16g, Carbohydrates 35g, Protein 15g, Allergens Gluten, Shellfish, Price 9.0
4.2 Mains:
4.2.1 Beef Burger (Grass-fed beef patty with lettuce, tomato, and cheese, served on a brioche bun): Calories 600 kcal, Fat 30g, Carbohydrates 40g, Protein 40g, Allergens Gluten, Dairy, Price 12.0
4.2.2 Vegetable Pasta (Whole wheat pasta tossed with seasonal vegetables in a light tomato sauce): Calories 420 kcal, Fat 12g, Carbohydrates 68g, Protein 14g, Allergens Gluten, Price 11.0
4.2.3 Grilled Salmon (Salmon fillet, grilled and served with a lemon dill sauce and steamed vegetables): Calories 520 kcal, Fat 28g, Carbohydrates 20g, Protein 50g, Allergens Fish, Price 15.0
4.2.4 Quinoa Salad (A hearty salad with quinoa, mixed greens, avocados, tomatoes, cucumbers, and a lemon vinaigrette): Calories 350 kcal, Fat 14g, Carbohydrates 45g, Protein 12g, Allergens None, Price 10.0
4.3 Alcoholic Drinks:
4.3.1 Craft Beer (Locally brewed IPA with citrus and pine notes): Calories 180 kcal, Fat 0g, Carbohydrates 14g, Protein 2g, Allergens Gluten, Price 5.0
4.3.2 Glass Of Red Wine (125 Ml) (Medium-bodied red wine with flavors of cherry and blackberry): Calories 125 kcal, Fat 0g, Carbohydrates 4g, Protein 0g, Allergens Sulfites, Price 7.0
4.3.3 Glass Of White Wine (125 Ml) (Crisp and refreshing white wine with hints of apple and pear): Calories 120 kcal, Fat 0g, Carbohydrates 3g, Protein 0g, Allergens Sulfites, Price 7.0
4.4 Non Alcoholic Drinks:
4.4.1 Lemonade (Freshly squeezed lemonade, sweetened with a touch of honey): Calories 120 kcal, Fat 0g, Carbohydrates 32g, Protein 0g, Allergens None, Price 3.0
4.4.2 Iced Tea (Cold-brewed black tea, served over ice with a lemon wedge): Calories 90 kcal, Fat 0g, Carbohydrates 24g, Protein 0g, Allergens None, Price 2.5
4.4.3 Fruit Smoothie (A blend of seasonal fruits, yogurt, and honey): Calories 200 kcal, Fat 2g, Carbohydrates 40g, Protein 5g, Allergens Dairy, Price 4.5
4.4.4 Sparkling Water (500 Ml) (Naturally carbonated spring water with a choice of lemon or lime): Calories 0 kcal, Fat 0g, Carbohydrates 0g, Protein 0g, Allergens None, Price 2.0
4.4.5 Tap Water (500 Ml) (Regular tap water): Calories 0 kcal, Fat 0g, Carbohydrates 0g, Protein 0g, Allergens None, Price 0.0
4.5 Hot Drinks:
4.5.1 Coffee (Freshly brewed coffee from single-origin beans): Calories 2 kcal, Fat 0g, Carbohydrates 0g, Protein 0.3g, Allergens None, Price 2.5
4.5.2 Green Tea (Steamed green tea, known for its antioxidants): Calories 0 kcal, Fat 0g, Carbohydrates 0g, Protein 0g, Allergens None, Price 2.0
4.5.3 Hot Chocolate (Rich and creamy hot chocolate, made with real cocoa and topped with whipped cream): Calories 250 kcal, Fat 12g, Carbohydrates 32g, Protein 8g, Allergens Dairy, Price 3.0
4.6 Desserts:
4.6.1 Chocolate Lava Cake (Warm, gooey chocolate cake with a molten chocolate center, served with vanilla ice cream): Calories 310 kcal, Fat 18g, Carbohydrates 34g, Protein 4g, Allergens Gluten, Eggs, Dairy, Price 6.0
4.6.2 Cheesecake (Creamy cheesecake on a graham cracker crust, topped with fresh berries): Calories 320 kcal, Fat 20g, Carbohydrates 26g, Protein 6g, Allergens Gluten, Eggs, Dairy, Price 5.5
4.6.3 Apple Pie (Classic apple pie with a flaky crust, served with a scoop of vanilla ice cream): Calories 350 kcal, Fat 17g, Carbohydrates 45g, Protein 3g, Allergens Gluten, Dairy, Price 5.0
5. Kids menu:
5.1 Starters:
5.1.1 Mini Cheese Quesadillas (Cheesy and delicious mini quesadillas, served with a side of salsa): Calories 150 kcal, Fat 9g, Carbohydrates 12g, Protein 7g, Allergens Dairy,Gluten, Price 4.0
5.1.2 Chicken Nuggets (Crispy chicken nuggets served with ketchup and honey mustard dipping sauces): Calories 200 kcal, Fat 12g, Carbohydrates 13g, Protein 10g, Allergens Gluten, Price 4.5
5.2 Mains:
5.2.1 Mac & Cheese (Creamy macaroni and cheese,a classic favorite): Calories 300 kcal, Fat 18g, Carbohydrates 25g, Protein 10g, Allergens Dairy,Gluten, Price 5.0
5.2.2 Mini Burgers (Three mini burgers on soft buns, served with fries): Calories 400 kcal, Fat 20g, Carbohydrates 35g, Protein 20g, Allergens Gluten, Price 6.0
5.3 Drinks:
5.3.1 Fruit Punch (Sweet and refreshing fruit punch made with real fruit juice): Calories 80 kcal, Fat 0g, Carbohydrates 20g, Protein 0g, Allergens None, Price 2.0
5.3.2 Milk (Cold,fresh milk. Choose from whole, 2%, or skim): Calories 100 kcal (for whole milk), Fat 5g (for whole milk), Carbohydrates 12g, Protein 8g, Allergens Dairy, Price 1.5
5.4 Desserts:
5.4.1 Ice Cream Sundae (Vanilla ice cream topped with chocolate syrup, whipped cream, and a cherry): Calories 250 kcal, Fat 15g, Carbohydrates 25g, Protein 5g, Allergens Dairy, Price 3.0
5.4.2 Fruit Cup (A mix of fresh seasonal fruits): Calories 90 kcal, Fat 0g, Carbohydrates 22g, Protein 1g, Allergens None, Price 2.5

We have a new customer. Their name is James Young, is 11 years old and is allergic to nothing
Hi!
```
   - For every customer message it will also run a semantic search on the vector DB and if found any relevant document (limited by the environment variable `VECTOR_DB_SEARCH_LIMIT` as long as the score is > `VECTOR_DB_MIN_SCORE`) and inject into the LLM prompt as a system message. That is to limit the amount of tokens passed to the LLM engine, for example:
     * Customer query: `do you have a pool table? what is the wifi password?`
     * The two documents returned by the vector DB are:
       - `dart-and-pool-table: Dart boards and pool tables available for guests. Challenge your friends or join a game. All are welcome!`
       - `wifi: Complimentary high-speed and free WiFi for all our guests`
     * The LLM engine can then provide a contextual relevant response as it now knows the dart/pool and wifi details:
```
Hello again,
Yes, we do have dart boards and pool tables available for our guests. Feel free to challenge your friends or join a game. We hope you'll enjoy this additional entertainment during your visit.
Regarding the WiFi, our high-speed internet is complimentary and free for all our guests. The WiFi network name is "StreamBite\_Guest" and the password is "StreamBiteFun123". We hope you enjoy staying connected during your time with us.
If you have any other questions, please let me know.
Best regards,
Steven Mayo
```
   - Once it receives the response from the LLM engine it will have it published into the topic `chatbot-chatbot_responses`

#### Web Application
The last python script is the web application (`src/webapp.py`):
 - It communicates with the back-end chatbot microservices using the [CQRS pattern](https://www.confluent.io/resources/ebook/designing-event-driven-systems)
 - After successfuly login, the customer messages will be published to the topic `chatbot-customer_actions` so it can be processed by the back-end microservices
 - It will also consume the messages from the topic `chatbot-chatbot_responses` matching the sessionID with the messageID (mid), then presenting it to the corresponding customer

All three python scripts have two logging handles, one to the console and another one to the Kafka topic `chatbot-logs`. The Web Application will consume all messages in that topic so it can be rendered when accessing http://localhost:8888/logs.

#### Changing the Policies Vector DB on the fly
To make any change on any on the tables, you can do so using your RDBMS of choice and make the changes. The demo is loaded with PgAdmin (http://localhst:5050. Username = `admin@admin.org` | Password = `admin`).

A [Postgres CDC source connector](https://docs.confluent.io/cloud/current/connectors/cc-postgresql-cdc-source-v2-debezium/cc-postgresql-cdc-source-v2-debezium.html) will make sure to capture any change (insert, update, delete) and have them published to Confluent Platform.

To see the changes in action, login to the Chatbot with a different user, or log out and log back in.

You can also have the log web interface open (http://localhost:8888/logs) and be able to see the changes as they happen, for example, after making a change on the table `public.extras` on `id` = `payment`:
```
[webapp] 2024-08-31 11:31:24,971.971 [INFO]
Loaded extras for payment: Accepts most major cards and mobile payments, cash or checks
[chatbot] 2024-08-31 11:31:25,011.011 [INFO]
Upserting Vector DB collection chatbot_restaurant: 329960943232017054634736035080607567292 | payment: Accepts most major cards and mobile payments, cash or checks
```

#### ksqlDB UDF
This demo also creates a ksqlDB UDF (User Defined Function) called `GET_VECTOR_DATA` (for details see: `src/udf/src/main/java/com/github/ifnesi/chatbot_restaurant/ksqldb/GetVectorData.java`). The purpose of the UDF is to call the REST API service `src/embeddings.py`. For now that UDF is not integrated with the application, but to see it in action:
- Go to Confluent Control Center's ksqlDB editor
- Create a stream with the customer's queries (topic `chatbot-customer_actions`):
```
CREATE STREAM `chatbot-customer_actions`WITH (
   KAFKA_TOPIC='chatbot-customer_actions',
   VALUE_FORMAT='AVRO'
);
```
- Call the UDF on the back of the customer's queries where the endpoint is the local embedding's REST API (`http://chatbot:9999/api/v1/embedding/sentence-transformer`):
```
SELECT `QUERY`, TRANSFORM(JSON_ITEMS(GET_VECTOR_DATA('http://chatbot:9999/api/v1/embedding/sentence-transformer', `QUERY`)), x => CAST(x AS DOUBLE)) as DATA FROM `chatbot-customer_actions` EMIT CHANGES;
```
- One example of response to the `SELECT` above is shown below:
```
{
  "QUERY": "can I bring my dog here?",
  "DATA": {
    "error": "false",
    "vector_data": [0.04148542508482933,0.006250734440982342,0.05819012224674225,0.021475134417414665,0.0020186242181807756,-0.016270723193883896,0.02578996866941452,-0.061915766447782516,-0.048213690519332886,-0.009008485823869705,0.04252133145928383,-0.051904186606407166,0.02813456580042839,0.09702321887016296,0.07315392792224884,0.030799560248851776,0.031287044286727905,-0.09311991930007935,-0.04645763710141182,-0.002092488808557391,-0.027973061427474022,0.060957249253988266,-0.038560692220926285,-0.008684077300131321,-0.0751216784119606,0.03147472068667412,0.020413193851709366,0.04908886179327965,0.020667489618062973,-0.012508911080658436,-0.0053960783407092094,-0.03953758254647255,-0.10351195186376572,0.01680070348083973,0.05262792855501175,0.019950225949287415,0.08291243761777878,-0.02666175737977028,0.07711523026227951,0.0636565312743187,0.024705730378627777,0.03539213910698891,0.039489127695560455,0.0056131090968847275,-0.040702082216739655,0.010486332699656487,-0.1020127534866333,-0.02981717698276043,0.08325967937707901,-0.051077429205179214,-0.023975979536771774,0.060145407915115356,0.03636021167039871,0.018633095547556877,-0.08663469552993774,-0.02067575417459011,0.027301616966724396,-0.08681748062372208,-0.06364648044109344,0.016057021915912628,-0.007570640183985233,0.058521516621112823,0.03655588999390602,0.01135778333991766,-0.02161017805337906,-0.06255520135164261,-0.03697717562317848,0.04377500340342522,0.062161337584257126,0.05131668597459793,0.0034493946004658937,0.09003595262765884,0.04132921248674393,0.019972342997789383,-0.00632896414026618,-0.08914203196763992,-0.04248828813433647,-0.009711802937090397,0.12172482907772064,-0.0002185339981224388,-0.014535952359437943,-0.012545671314001083,-0.02455935813486576,0.00566560635343194,0.011099562980234623,0.05956951156258583,0.027331121265888214,0.046070218086242676,-0.06350277364253998,0.0058051822707057,0.008004616014659405,-0.1173870787024498,0.03656063973903656,0.009626222774386406,-0.044913701713085175,-0.08998951315879822,-0.08279511332511902,-0.0396212600171566,-0.018645992502570152,0.0318099707365036,0.036705173552036285,0.007503211963921785,0.019838783890008926,0.0016287729376927018,0.04281947761774063,-0.01650247909128666,-0.008059607818722725,0.0570027120411396,0.004940525162965059,0.03778237849473953,-0.05338146165013313,0.034492939710617065,0.046380165964365005,0.029171139001846313,0.06289961189031601,0.05608459934592247,-0.04469870775938034,-0.07387876510620117,-0.058510009199380875,-0.14185406267642975,0.044735316187143326,-0.02478071115911007,0.00957561656832695,0.04095771163702011,0.06807125359773636,-0.08344490826129913,-0.03324950486421585,-6.567810198990596E-33,0.03529994562268257,-0.011170128360390663,-0.0450899638235569,-0.03429943323135376,0.04541560262441635,0.02830183506011963,-0.0019182353280484676,-0.024886425584554672,-0.040451157838106155,-0.07418853044509888,0.014311284758150578,-0.00326817249879241,0.06640776246786118,-0.06638824939727783,-0.03465382009744644,0.0675661712884903,0.08300627768039703,-0.051105841994285583,0.08644999563694,-0.06666924804449081,-0.01334446482360363,-0.1291804313659668,0.038507454097270966,0.02860092557966709,-0.006278979126363993,0.03114325739443302,-0.034012794494628906,-0.024899981915950775,0.01078324019908905,0.010056441649794579,-0.04224738851189613,0.013905108906328678,-0.021522626280784607,0.04892240837216377,-0.04301802068948746,0.007357743103057146,-0.027122316882014275,-0.05326302349567413,-0.0359811894595623,0.05710654705762863,0.03494929522275925,-0.020873721688985825,0.023145420476794243,0.07465005666017532,0.012709226459264755,-0.006486289668828249,0.05550714582204819,-0.04158461093902588,-0.051222193986177444,-0.04532526060938835,-0.05494895204901695,-0.004527107812464237,0.038040872663259506,-0.06329845637083054,0.010155632160604,0.020422814413905144,0.0923951268196106,0.04585942625999451,0.0876770168542862,0.006878805812448263,0.05166168510913849,0.025501878932118416,0.027169136330485344,0.04038870707154274,0.05382927507162094,-0.1330927312374115,-0.06479690223932266,0.014212463051080704,-0.015539157204329967,0.000031297382520278916,0.039306603372097015,0.009844171814620495,-0.039434973150491714,0.007487842347472906,0.07249511033296585,-0.0316191241145134,0.000943477323744446,0.0517764650285244,0.0863514244556427,-0.09601826220750809,-0.003509717294946313,-0.03410576656460762,-0.07505938410758972,0.10793422162532806,0.0466645285487175,0.03386357054114342,-0.021222269162535667,-0.02237270399928093,-0.06338601559400558,0.016828708350658417,-0.047067176550626755,-0.04838157817721367,0.044201336801052094,-0.12207841873168945,0.021221403032541275,3.065422025650706E-33,0.06229116767644882,0.022888848558068275,0.048943039029836655,-0.0033382370602339506,-0.006035309284925461,0.00492662051692605,0.006260236259549856,0.02861839346587658,0.020945090800523758,0.05715595558285713,-0.09761392325162888,0.05711362510919571,0.10949987918138504,-0.00827774591743946,0.06169615313410759,0.030791910365223885,-0.00834592618048191,0.012348747812211514,-0.014936495572328568,-0.040073689073324203,-0.13140632212162018,0.044285938143730164,0.06220126524567604,0.02852167934179306,-0.04860337823629379,0.06498923897743225,0.03720441833138466,-0.013392558321356773,-0.023769278079271317,-0.09390944987535477,-0.0038950364105403423,-0.08830422908067703,-0.009800530038774014,0.03598659113049507,-0.021834129467606544,0.03605914115905762,0.06211795657873154,-0.06788846105337143,-0.05318380147218704,0.020077593624591827,0.001151377335190773,-0.02062768116593361,-0.05536618083715439,0.08116194605827332,0.002001719083636999,0.07208152115345001,0.004003269597887993,-0.07922951877117157,0.04201778024435043,0.006377509329468012,-0.0683927834033966,0.01856602542102337,-0.039948489516973495,-0.09479702264070511,-0.020575320348143578,0.018104348331689835,-0.053825270384550095,-0.036937110126018524,0.05879238620400429,-0.03723985329270363,0.005618886556476355,0.015460189431905746,0.005793137010186911,0.028490116819739342,-0.0036521372385323048,-0.1039818748831749,-0.03237728029489517,0.019714606925845146,0.06045322120189667,-0.046932402998209,-0.06990240514278412,0.013962887227535248,-0.055486131459474564,-0.019895531237125397,0.06101064383983612,0.039583150297403336,0.1256321519613266,0.0011419024085626006,0.022616375237703323,-0.08701580762863159,-0.0021294921170920134,-0.06564299017190933,-0.019148634746670723,-0.039117150008678436,0.10233641415834427,-0.04432031512260437,0.021077526733279228,0.010237420909106731,0.017337460070848465,-0.05155212804675102,0.008304983377456665,0.08711759746074677,0.0058873738162219524,-0.07543926686048508,-0.016404055058956146,-1.4223561883852653E-8,-0.03250569850206375,0.03757759556174278,-0.020564712584018707,-0.004865516442805529,0.015287613496184349,0.031210951507091522,-0.04298065975308418,-0.1063687801361084,-0.020220939069986343,0.09376803040504456,0.00568140996620059,-0.056748997420072556,-0.05445292964577675,0.009404884651303291,-0.040409475564956665,0.04905899986624718,0.007222361396998167,0.005415207706391811,0.0035104448907077312,0.06998180598020554,-0.1101081445813179,0.04658801853656769,0.06451233476400375,0.04572039097547531,-0.010689090006053448,-0.00711607513949275,-0.02479802817106247,-0.02383127622306347,0.02095096744596958,0.07235948741436005,-0.08903738856315613,0.07985281944274902,-0.09510514885187149,0.06390991806983948,-0.014556282199919224,-0.1644059121608734,0.026550933718681335,-0.04452081769704819,-0.006570060737431049,-0.011723089963197708,-0.0010170690948143601,0.07410905510187149,-0.10411840677261353,0.03319982439279556,0.022939670830965042,0.016982892528176308,-0.010104750283062458,-0.05849899351596832,-0.007545189931988716,-0.005234439391642809,-0.1319713294506073,-0.019663913175463676,0.03780777007341385,-0.0003622904478106648,0.04631851240992546,0.06483791768550873,-0.019332943484187126,-0.07252217084169388,0.05386349931359291,0.055277712643146515,-0.0297841913998127,0.01983148232102394,0.052006885409355164,-0.002363412408158183],
    "status_code": "200"
  }
}
```
- For more details about that UDF execute the following ksqlDB query `describe function GET_VECTOR_DATA;`, the result is show below:
```
{
  "@type": "describe_function",
  "statementText": "describe function GET_VECTOR_DATA;",
  "name": "GET_VECTOR_DATA",
  "description": "Calls a REST API to generate embeddings from a given text input",
  "author": "Italo Nesi",
  "version": "1.0.0",
  "path": "/etc/ksqldb/ext/udf-1.0.0-jar-with-dependencies.jar",
  "functions": [
    {
      "arguments": [
        {
          "name": "apiUrl",
          "type": "VARCHAR",
          "description": "URL for REST API service",
          "isVariadic": false
        },
        {
          "name": "sentence",
          "type": "VARCHAR",
          "description": "Sentence to generate the vector data",
          "isVariadic": false
        }
      ],
      "returnType": "VARCHAR",
      "description": "Generate embeddings for a text by calling an external REST API",
      "argumentTypes": [
        "VARCHAR",
        "VARCHAR"
      ]
    }
  ],
  "type": "SCALAR",
  "warnings": [

  ]
}
```

### Stopping the demo
To stop the demo, please run `./demo.sh -p`.

```
2024-09-17 15:17:53.000 [INFO]: Stopping docker compose

[+] Running 13/13
 ✔ Container ksqldb-cli                     Removed
 ✔ Container pgadmin                        Removed
 ✔ Container chatbot-restaurant-connect2-1  Removed
 ✔ Container ksqldb-server                  Removed
 ✔ Container postgres                       Removed
 ✔ Container chatbot                        Removed
 ✔ Container qdrant                         Removed
 ✔ Container control-center                 Removed
 ✔ Container chatbot-restaurant-connect-1   Removed
 ✔ Container schema-registry                Removed
 ✔ Container broker                         Removed
 ✔ Container zookeeper                      Removed
 ✔ Network chatbot-restaurant_default       Removed

2024-09-17 15:18:32.000 [INFO]: Demo successfully stopped
```

## Runtime Demo and Screenshots
### Demo
![image](docs/demo.gif)

### Login screen
![image](docs/login.png)

### Customer Profiles
To access that page go to http://localhost:8888/profiles (password is the same as the username)
![image](docs/profiles.png)

### Initial message after login
![image](docs/initial_message.png)

### Asking for the main menu
![image](docs/main_menu.png)

### Going through some of the restaurant policies
![image](docs/policies.png)

### System logs
They can be accessed through http://localhost:8888/logs. All applications are producing logs to Confluent Platform and the web application is consuming them, adding to a local queue and off-loading the queue once the logs page is opened (logs are refreshed at every 500ms)
![image](docs/logs.png)

## External References
Check out [Confluent's Developer portal](https://developer.confluent.io), it has free courses, documents, articles, blogs, podcasts and so many more content to get you up and running with a fully managed Apache Kafka service.

Disclaimer: I work for Confluent :wink: