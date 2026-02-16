from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
from dotenv import load_dotenv
from gtts import gTTS
from difflib import SequenceMatcher
from groq import Groq
import uuid
import re
import json
from datetime import datetime
import random
import atexit
import signal
import secrets

# ================= SETUP =================
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app = Flask(__name__)
# Use environment variable or generate secure random key
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Separate conversation contexts for each mode
conversation_contexts = {}  # Format: {user_id: {'conversation': '', 'roleplay': ''}}

# User database
users_db = {}

# Teacher database (now includes registered teachers)
teachers_db = {}

# Progressive XP requirements
def get_xp_for_level(level):
    """Calculate total XP required to reach a level"""
    if level <= 1:
        return 0
    xp = 0
    for l in range(1, level):
        if l == 1:
            xp += 25
        else:
            xp += 30
    return xp

def calculate_level(xp):
    """Calculate level based on current XP"""
    level = 1
    while xp >= get_xp_for_level(level + 1):
        level += 1
    return level

def get_xp_for_next_level(current_level):
    """Get XP required for next level"""
    if current_level == 1:
        return 25
    else:
        return 30

def get_difficulty_for_level(level):
    """Auto-adjust difficulty based on level"""
    if level <= 2:
        return "easy"
    elif level <= 4:
        return "easy"
    elif level <= 7:
        return "medium"
    elif level <= 10:
        return "medium"
    else:
        return "hard"

def save_user_progress(user_id, stars_earned, mode):
    """Save user progress and update XP"""
    if user_id in users_db:
        old_level = users_db[user_id]['level']
        users_db[user_id]['total_xp'] += stars_earned
        users_db[user_id]['total_stars'] += stars_earned
        new_level = calculate_level(users_db[user_id]['total_xp'])
        users_db[user_id]['level'] = new_level
        users_db[user_id]['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if mode not in users_db[user_id]['mode_stats']:
            users_db[user_id]['mode_stats'][mode] = {'stars': 0, 'sessions': 0}
        
        users_db[user_id]['mode_stats'][mode]['stars'] += stars_earned
        users_db[user_id]['mode_stats'][mode]['sessions'] += 1
        
        save_database()
        
        return {
            'leveled_up': new_level > old_level,
            'new_level': new_level,
            'old_level': old_level
        }
    return None

def save_database():
    """Save databases to JSON files with improved error handling"""
    try:
        # Save users database
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(users_db, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        
        # Save teachers database
        with open('teachers_data.json', 'w', encoding='utf-8') as f:
            json.dump(teachers_db, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"Database saved successfully at {datetime.now()}")
        print(f"Users in DB: {len(users_db)}, Teachers in DB: {len(teachers_db)}")
    except Exception as e:
        print(f"ERROR saving database: {e}")
        import traceback
        traceback.print_exc()

def load_database():
    """Load databases from JSON files with improved error handling"""
    global users_db, teachers_db
    try:
        if os.path.exists('users_data.json'):
            with open('users_data.json', 'r', encoding='utf-8') as f:
                loaded_users = json.load(f)
                users_db = loaded_users
                print(f"Loaded {len(users_db)} users from database")
        else:
            print("No users_data.json found, starting with empty database")
            users_db = {}
        
        if os.path.exists('teachers_data.json'):
            with open('teachers_data.json', 'r', encoding='utf-8') as f:
                loaded_teachers = json.load(f)
                teachers_db = loaded_teachers
                print(f"Loaded {len(teachers_db)} teachers from database")
        else:
            print("No teachers_data.json found, starting with empty database")
            teachers_db = {}
    except Exception as e:
        print(f"ERROR loading database: {e}")
        import traceback
        traceback.print_exc()
        users_db = {}
        teachers_db = {}

load_database()

# Register cleanup handlers to save on exit
def cleanup_handler(signum=None, frame=None):
    """Save database on program exit"""
    print("Saving database before exit...")
    save_database()

atexit.register(cleanup_handler)
signal.signal(signal.SIGTERM, cleanup_handler)
signal.signal(signal.SIGINT, cleanup_handler)

def get_user_context(user_id, mode):
    """Get conversation context for specific user and mode"""
    if user_id not in conversation_contexts:
        conversation_contexts[user_id] = {'conversation': '', 'roleplay': ''}
    return conversation_contexts[user_id].get(mode, '')

def update_user_context(user_id, mode, context):
    """Update conversation context for specific user and mode"""
    if user_id not in conversation_contexts:
        conversation_contexts[user_id] = {'conversation': '', 'roleplay': ''}
    conversation_contexts[user_id][mode] = context[-1200:]  # Keep last 1200 chars

# ================= TTS =================
def speak_to_file(text, slow=False):
    os.makedirs("static/audio", exist_ok=True)
    filename = f"{uuid.uuid4()}.mp3"
    path = f"static/audio/{filename}"
    gTTS(text=text, lang="en", slow=slow).save(path)
    return "/" + path

# ================= AI FUNCTIONS WITH ISOLATED MEMORY =================

def english_coach(child_text, user_id):
    """Conversation mode with isolated memory per user"""
    context = get_user_context(user_id, 'conversation')
    
    prompt_variations = [
        "make the response natural and conversational",
        "use different words than previous responses",
        "be creative with your follow-up question",
        "vary your praise words",
        "ask about different topics each time"
    ]
    variation_hint = random.choice(prompt_variations)

    prompt = f"""
You are an English speaking coach for children aged 6 to 15.

STRICT RULES:
- Always correct the child's sentence
- If only one word, make a full sentence
- Very simple English
- Encourage the child with VARIED praise words
- Ask ONE follow-up question about DIFFERENT topics each time
- No grammar explanation
- {variation_hint}

Respond ONLY in this format:

CORRECT: <correct sentence>
PRAISE: <short encouragement - use different words>
QUESTION: <one simple question about a NEW topic>

Conversation so far:
{context}

Child says:
"{child_text}"
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        top_p=0.9
    )

    reply = response.choices[0].message.content.strip()
    new_context = context + f"\nChild: {child_text}\nAssistant: {reply}"
    update_user_context(user_id, 'conversation', new_context)
    
    return reply

def roleplay_coach(child_text, roleplay_type, user_id):
    """Roleplay mode with isolated memory per user"""
    context = get_user_context(user_id, 'roleplay')

    # UPDATED: Title-specific roles with domain-specific questions
    roles = {
        "teacher": """
You are a kind school teacher.
Help the student learn English.
Ask VARIED study-related questions SPECIFICALLY about:
- Different academic subjects (Math, Science, History, Geography, Literature)
- Study habits and homework
- School projects and assignments
- Educational goals and interests
- Learning challenges and achievements
Each question should be about a DIFFERENT academic topic.
Be encouraging and patient.
Stay strictly in teacher role.
""",
        "friend": """
You are a friendly classmate.
Talk casually and happily.
Ask about DIFFERENT personal topics SPECIFICALLY like:
- Favorite hobbies and activities
- Weekend plans and adventures
- Favorite games, movies, or books
- Sports and outdoor activities
- Personal interests and collections
- Family activities and pets
Each question should be about a DIFFERENT casual topic.
Be cheerful and supportive.
Stay strictly in friend role.
""",
        "interviewer": """
You are a job interviewer.
Be polite and professional.
Ask DIFFERENT professional questions SPECIFICALLY about:
- Career goals and aspirations
- Skills and strengths
- Work experience (even if limited)
- Problem-solving abilities
- Teamwork and leadership
- Future plans and ambitions
Each question should be a DIFFERENT interview topic.
Be encouraging but maintain professional tone.
Stay strictly in interviewer role.
""",
        "viva": """
You are a viva examiner.
Ask DIFFERENT academic project questions SPECIFICALLY about:
- Project objectives and goals
- Research methodology
- Findings and results
- Challenges faced
- Applications and implications
- Future scope and improvements
Each question should probe a DIFFERENT aspect of academic work.
Focus on understanding various project dimensions.
Be fair and encouraging while maintaining examiner professionalism.
Stay strictly in viva examiner role.
"""
    }

    role_instruction = roles.get(roleplay_type, "You are a friendly English speaking partner.")
    variety_hints = [
        "Ask about something you haven't asked before in this conversation",
        "Use different question words than your previous questions",
        "Focus on a completely different aspect of your role",
        "Be creative and probe a new dimension",
        "Explore an unexplored area relevant to your role"
    ]
    variety_hint = random.choice(variety_hints)

    prompt = f"""
{role_instruction}

You are doing roleplay with a student aged 6 to 15.

STRICT RULES:
- Always correct the student's sentence
- Very simple English
- Stay STRICTLY in your role
- Ask questions ONLY related to your specific role domain
- Encourage the student with VARIED praise
- Ask ONE role-specific question from your domain
- No grammar explanation
- {variety_hint}

Respond ONLY in this format:

CORRECT: <correct sentence>
PRAISE: <short encouragement - vary your words>
QUESTION: <one role-specific question about a NEW topic from your domain>

Conversation so far:
{context}

Student says:
"{child_text}"
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        top_p=0.9
    )

    reply = response.choices[0].message.content.strip()
    new_context = context + f"\nStudent: {child_text}\nAssistant: {reply}"
    update_user_context(user_id, 'roleplay', new_context)
    
    return reply

# ================= REPEAT & SPELL BEE FUNCTIONS =================
def generate_repeat_sentence(category="general", difficulty="easy", user_level=1):
    """Generate sentences with 150+ options per difficulty - NO AI, pure random selection"""
    
    # Use the difficulty selected by the user directly - no level-based override
    actual_difficulty = difficulty
    
    # MASSIVELY EXPANDED SENTENCE POOLS - 150+ per difficulty level
    # Easy: 3-5 words | Medium: 8-15 words | Hard: 18-32 words
    
    all_easy_sentences = [
        # 3-5 word sentences (150 total)
        "I love ice cream", "The sun shines bright", "Mom reads books daily", "Birds sing beautiful songs",
        "We play fun games", "Rain feels very cold", "Trees grow very tall", "Flowers smell so nice",
        "Cats sleep all day", "Dogs wag their tails", "Stars shine at night", "Kids laugh very loud",
        "Dad drives the car", "Baby cries very loud", "Wind blows quite hard", "Snow falls from sky",
        "Fish swim really fast", "Bees make sweet honey", "Moon looks very round", "Clouds float up high",
        "I drink cold water", "She eats her lunch", "He rides a bike", "They watch the TV",
        "We go back home", "Birds fly to south", "Bells ring very loud", "Doors open really wide",
        "Windows are very clean", "Lights turn on now", "Music sounds really good", "Food tastes quite great",
        "Air smells so fresh", "Grass feels very soft", "Ice is very cold", "Fire burns so hot",
        "Books help us learn", "Pens write very well", "Paper is quite thin", "Glue sticks things tight",
        "Scissors cut the paper", "Crayons draw nice pictures", "Paint is very colorful", "Brushes are quite soft",
        "Cups hold the water", "Plates hold the food", "Spoons are very helpful", "Forks work quite well",
        "Knives cut the bread", "Bowls are very round", "Pots cook the food", "Pans fry the eggs",
        "Beds are very soft", "Pillows feel so nice", "Blankets keep us warm", "Sheets are very clean",
        "Chairs support us well", "Tables hold many things", "Lamps give bright light", "Fans cool the rooms",
        "Clocks tell the time", "Watches show the hours", "Calendars show all dates", "Maps show many places",
        "Pictures look very nice", "Mirrors reflect the light", "Carpets cover the floors", "Curtains block the sun",
        "Plants need fresh water", "Gardens grow good food", "Seeds become tall plants", "Fruits taste very sweet",
        "Vegetables are quite healthy", "Bread is very soft", "Cheese tastes really good", "Milk builds strong bones",
        "Water quenches our thirst", "Juice is very sweet", "Tea is quite warm", "Coffee smells really good",
        "Cars move very fast", "Buses carry many people", "Trains run quite long", "Planes fly up high",
        "Boats float on water", "Ships are very big", "Trucks haul heavy cargo", "Bikes save good energy",
        "Roads connect many places", "Bridges cross big rivers", "Tunnels go straight through", "Streets are very busy",
        "Stores sell many things", "Markets are quite crowded", "Shops have good goods", "Malls are very large",
        "Schools teach all students", "Teachers help us learn", "Books contain much knowledge", "Pencils write the words",
        "Erasers remove the mistakes", "Rulers measure the length", "Compasses draw nice circles", "Calculators solve hard math",
        "Computers process the data", "Keyboards type the letters", "Mice click the buttons", "Screens display the information",
        "Phones make the calls", "Radios play good music", "Cameras take nice pictures", "Videos show good motion",
        "Letters deliver the messages", "Packages contain the items", "Envelopes hold the letters", "Stamps cost some money",
        "Money buys many things", "Coins are made metal", "Bills are made paper", "Banks keep things safe",
        "Doctors treat the patients", "Nurses care for people", "Hospitals heal sick people", "Medicine makes us better",
        "Police keep us safe", "Firefighters stop big fires", "Soldiers protect our country", "Heroes save many lives",
        "Farmers grow good crops", "Workers build many things", "Artists create such beauty", "Musicians make good music",
        "Dancers move very gracefully", "Singers have nice voices", "Actors perform great plays", "Writers pen good stories",
        "Cooks prepare the meals", "Bakers make fresh bread", "Chefs create nice dishes", "Waiters serve the food",
        "Pilots fly the planes", "Sailors navigate the ships", "Drivers steer the vehicles", "Captains lead the teams",
        "Friends share their toys", "Families eat together daily", "Neighbors help each other", "People work very hard"
    ]
    
    all_medium_sentences = [
        # 8-12 word sentences (150 total)
        "I always brush my teeth carefully every single morning before going to school",
        "The beautiful blue sky looks absolutely stunning today with no clouds at all",
        "My best friend always helps me complete my homework assignments after school ends",
        "We enjoy watching interesting movies together every single weekend at our comfortable home",
        "The public library has thousands of fascinating books available for everyone to read freely",
        "I practice playing the piano diligently right after school ends every single day",
        "My grandmother tells wonderful bedtime stories every night before we go to sleep peacefully",
        "The grocery store always sells fresh vegetables and fruits every single day without fail",
        "Children play happily together in the park every sunny afternoon outside with their friends",
        "Our dedicated teacher explains difficult lessons very clearly to all students in the classroom",
        "The mailman delivers letters and packages every afternoon punctually at three o'clock sharp each day",
        "My talented sister bakes delicious chocolate chip cookies for us very often at home",
        "The beautiful garden flowers bloom magnificently during the lovely springtime every single year naturally",
        "Students study very hard for all their important exams regularly throughout the entire academic year",
        "Basketball players practice their shooting skills diligently every single day after school in the gym",
        "The kind librarian helps students find interesting books in the very large library every day",
        "We celebrate birthdays with cake and candles together joyfully as a happy loving family",
        "Colorful butterflies dance gracefully around the blooming flowers in the beautiful garden outside our house",
        "My energetic puppy loves playing fetch in the backyard every single afternoon when weather permits",
        "The school cafeteria serves hot nutritious meals to all students every single day at lunchtime",
        "Brave firefighters respond quickly to all emergency calls immediately without any delay or hesitation whatsoever",
        "The museum displays ancient artifacts that are carefully preserved for all future generations to see",
        "Local farmers sell fresh organic vegetables at the farmers market every weekend to local residents",
        "My uncle fixes broken computers very skillfully in his workshop every day with special tools",
        "The community swimming pool opens early during the warm summer months for all swimmers daily",
        "We recycle plastic bottles regularly to help protect our precious environment for all future generations",
        "The friendly dentist checks teeth for cavities twice every year very carefully and thoroughly always",
        "My cousin collects colorful stamps from many different countries around the world quite enthusiastically regularly",
        "The dedicated park ranger protects wildlife in the forest every single day rain or shine",
        "We plant trees regularly to make our city much greener for everyone living here today",
        "The busy bakery opens at six o'clock every single morning selling delicious fresh bread daily",
        "Doctors recommend eating fruits and vegetables daily regularly for maintaining good health and wellness always",
        "The traffic light helps people cross busy streets safely every single day without any accidents",
        "Astronauts train for many years before going to space on exciting special dangerous missions regularly",
        "My neighbor waters her beautiful garden every single evening after work ends without fail daily",
        "The skilled mechanic repairs cars in his busy workshop throughout the day using various tools",
        "Librarians organize books alphabetically on tall wooden shelves in the large library very carefully always",
        "We save money in piggy banks for our future dreams and important goals every week",
        "The postman delivers packages rain or shine very faithfully every single afternoon at three o'clock",
        "Scientists conduct important experiments in their laboratories very carefully every single day to discover new things",
        "Athletes warm up properly before competing in big tournaments to prevent any possible physical injuries",
        "The veterinarian treats sick animals with gentle care in the animal clinic every day carefully",
        "Musicians practice scales and songs many hours every single day to improve their musical skills",
        "The janitor cleans classrooms thoroughly every single evening after students leave school for the day",
        "Photographers capture beautiful moments with their expensive digital cameras at special events and celebrations always",
        "The conductor leads the orchestra through complex symphonies during concert performances every night with precision",
        "Volunteers help organize community events for free very willingly to help other people in need",
        "The architect designs buildings using special computer programs in the office every day for clients",
        "Lifeguards watch swimmers carefully at the busy crowded beach during summer vacation months every day",
        "The florist arranges beautiful bouquets for special occasions like weddings and birthdays every single day",
        "Engineers solve difficult problems using mathematics and physics every day in their office workspace carefully",
        "The jeweler repairs watches and necklaces very carefully in the small workshop using delicate tools",
        "Pilots check aircraft systems before every single flight to ensure passenger safety always without exception",
        "The tailor sews custom clothes using traditional techniques in the shop every day for customers",
        "Electricians install wiring in new houses very safely following all building codes strictly every day",
        "The optometrist tests vision and prescribes eyeglasses accurately for patients every single day at the clinic",
        "Geologists study rocks and minerals from different regions around the world every day in laboratories",
        "The zookeeper feeds animals according to special schedules in the zoo every day without missing",
        "Carpenters build furniture using quality wood and tools in workshops throughout the day for clients",
        "The locksmith makes duplicate keys very precisely using special machines every single day for customers",
        "Translators convert text from one language to another accurately for business clients every day carefully",
        "The choreographer creates beautiful dance routines for performances with dancers every single week for shows",
        "Journalists write news articles about current important events happening around the world every single day",
        "The accountant manages financial records using special software in the office every day for companies",
        "Historians research past events using ancient documents very carefully in libraries and archives every day",
        "The therapist helps people overcome their personal challenges through counseling sessions regularly every week carefully",
        "Programmers write complex computer code for useful applications on computers every single day at work",
        "The sommelier recommends perfect wines for gourmet meals at expensive restaurants every evening to customers",
        "Astronomers observe distant stars through powerful telescopes at the observatory every single night when clear",
        "The curator preserves valuable artwork in the museum with great care every day for posterity",
        "Botanists study different plant species in tropical rainforests on research expeditions regularly every year carefully",
        "The conductor ensures trains depart on schedule punctually from the station every single day without delays",
        "Surgeons perform delicate operations in sterile operating rooms at hospitals every single day to save lives",
        "The decorator arranges furniture to maximize room space in houses for clients regularly every week",
        "Nutritionists plan healthy balanced meals for various clients with special dietary needs every day carefully",
        "The auctioneer sells valuable items to highest bidders at auctions every single weekend with enthusiasm",
        "Zoologists observe animal behavior in their natural habitats on research expeditions every year in forests",
        "The barista prepares specialty coffee drinks with skill at the cafe every morning for customers",
        "Psychologists help patients understand their emotions and thoughts during therapy sessions every week with compassion",
        "The landscaper designs beautiful gardens using native plants for homeowners in the area every season",
        "Astronomers calculate distances to faraway galaxies using mathematics at the observatory every night when possible",
        "The receptionist greets visitors with friendly warm smiles at the office every day without fail",
        "Archaeologists excavate ancient ruins very carefully with brushes on research expeditions every summer in deserts",
        "The coach motivates athletes to achieve their best performance during practice sessions every day passionately",
        "Paramedics provide emergency medical care at accident scenes throughout the city every day to victims",
        "The editor reviews manuscripts for grammar and clarity for publishing companies every week very carefully",
        "Marine biologists study ocean creatures in deep waters on research vessels regularly throughout the year",
        "The conductor keeps musicians playing together in harmony during orchestra performances every night with skill",
        "Geographers create detailed maps showing terrain and features using modern technology every day in offices",
        "The referee enforces rules fairly during sports games to ensure fair play always without bias",
        "Paleontologists discover dinosaur fossils buried underground for millions of years on expeditions regularly every summer",
        "The counselor helps students choose appropriate career paths for their future success in life carefully",
        "Ornithologists study bird migration patterns across multiple continents on research projects every year with dedication",
        "The sommelier pairs wines with dishes perfectly every time at fancy restaurants for customers",
        "Meteorologists forecast weather patterns using satellite data at the station every single day accurately",
        "The librarian organizes book collections and helps visitors find resources every day with patience",
        "Chefs prepare gourmet meals using fresh ingredients in restaurant kitchens every evening for diners",
        "The pharmacist fills prescriptions accurately and provides medical advice to patients every day at drugstores",
        "Teachers create lesson plans and instruct students in classrooms five days every week patiently",
        "The mechanic diagnoses car problems using diagnostic tools in the shop every day for clients",
        "Nurses care for patients and administer medications in hospitals twenty four hours every day",
        "The gardener maintains landscapes and prunes plants for clients throughout the week regularly with care",
        "Dentists examine teeth and perform procedures in clinics five days every single week for patients",
        "The artist creates paintings and sculptures in the studio workspace every single day with passion",
        "Pilots navigate aircraft safely through airspace on scheduled flights every single day for passengers",
        "The writer composes articles and stories on the computer every day for various publications regularly",
        "Engineers design structures and systems using computer programs in offices every working day for projects",
        "The security guard patrols buildings protecting property from theft every single night throughout the area",
        "Coaches train athletes in various sports teaching them techniques and strategies every day at gyms",
        "The florist creates beautiful arrangements combining flowers and greenery for events every week with creativity",
        "Mechanics replace worn parts and service vehicles in repair shops every day for different customers",
        "The tour guide shows visitors historical sites explaining their significance every day with great enthusiasm",
        "Bankers manage accounts and provide financial advice to clients every day at the branch office",
        "The seamstress alters clothing ensuring perfect fits for customers every day in the small shop",
        "Firefighters train regularly practicing rescue techniques to stay prepared for emergencies every single week diligently",
        "The plumber fixes leaks and installs fixtures in homes and businesses every day using tools",
        "Veterinary technicians assist doctors caring for animals in clinics every day with gentle hands",
        "The electrician troubleshoots wiring problems and makes repairs safely every day for various clients regularly",
        "Pharmacists counsel patients about medications explaining proper dosage and side effects every day carefully",
        "The taxi driver navigates city streets transporting passengers to their destinations every day safely",
        "Construction workers build structures following blueprints and safety protocols every day on various job sites",
        "The hairstylist cuts and styles hair creating new looks for clients every day at salon",
        "Postal workers sort and deliver mail to homes and businesses every day regardless of weather",
        "The paramedic responds to medical emergencies providing care to patients every day throughout the city",
        "Scientists analyze data from experiments drawing conclusions that advance knowledge every day in laboratories carefully",
        "The yoga instructor teaches poses and breathing techniques to students in classes every day patiently",
        "Electricians wire new buildings ensuring proper installation of electrical systems every day on construction sites",
        "The physical therapist helps patients recover from injuries through exercise programs every day with encouragement",
        "Social workers connect families with resources and support services every day in the community office",
        "The chef experiments with flavors creating innovative dishes for restaurant menus every day with creativity",
        "Warehouse workers organize inventory and fill orders accurately every day in the large storage facility",
        "The massage therapist relieves muscle tension using various techniques for clients every day at spa",
        "Graphic designers create visual content for websites and advertisements every day using computer software",
        "The optician helps customers select frames and adjusts eyeglasses for comfort every day at store",
        "Real estate agents show properties to potential buyers explaining features every day throughout the neighborhood",
        "The personal trainer develops workout plans helping clients achieve fitness goals every day at gym",
        "Emergency dispatchers coordinate responses directing help to those in need every day from call center",
        "The flight attendant ensures passenger safety and comfort during flights every day with professional courtesy",
        "Lab technicians conduct tests analyzing samples for medical diagnoses every day in hospital laboratories carefully",
        "The event planner organizes celebrations coordinating details to create memorable experiences every week for clients",
        "Firefighters inspect buildings checking safety equipment and identifying hazards every week in the community thoroughly",
        "The guidance counselor advises students on academic and personal matters every day in school offices",
        "Web developers create and maintain websites ensuring functionality and user experience every day at companies"
    ]
    
    all_hard_sentences = [
        # 15-25 word sentences (150 total - TRULY CHALLENGING!)
        "My absolute favorite hobby is drawing extremely colorful and detailed pictures in my special sketchbook every single evening after I finish all my homework",
        "Every Sunday evening I help my mother prepare delicious homemade dinner for our entire extended family who regularly gather at our house to celebrate being together",
        "During the wonderful summer vacation we visit interesting historical places and fascinating museums and take lots of memorable photographs to preserve those precious moments forever in albums",
        "The incredibly hardworking farmer wakes up very early every single morning to water the crops and check for any harmful pests or plant diseases in the fields",
        "My younger brother genuinely enjoys reading exciting adventure storybooks with thrilling plots before going to sleep at night in his comfortable and cozy bed with soft pillows",
        "The magnificent butterfly with beautiful colorful wings flew gracefully across our blooming garden yesterday afternoon while we watched in complete amazement and wonder at its elegant movements",
        "Professional musicians dedicate countless hours every single day to practicing their instruments and perfecting extremely complex musical compositions for their upcoming important concerts and public performances worldwide",
        "The experienced chef carefully prepares elaborate multi course meals using fresh organic ingredients sourced from local sustainable farms in the surrounding region to ensure quality and taste",
        "Ancient civilizations built magnificent pyramids and impressive temples using primitive tools and basic techniques that still absolutely amaze modern architects historians and engineers even today after thousands of years",
        "The dedicated scientist conducts meticulous laboratory experiments every day to develop new medicines and treatments that could potentially save countless precious human lives worldwide and cure diseases",
        "Talented professional athletes undergo rigorous intensive training programs for many years to compete at the highest levels in prestigious international sporting competitions and win gold medals for countries",
        "The passionate teacher explains difficult mathematical concepts using creative visual aids and interactive demonstrations to help students understand better and succeed in their academic studies and examinations",
        "Skilled artisans handcraft beautiful intricate jewelry pieces using precious metals and gemstones that have been carefully selected for their exceptional quality beauty and lasting durability over many generations",
        "The curious child asked numerous thoughtful questions about the mysterious universe and how different celestial bodies interact with each other in the vast expanse of outer space",
        "Experienced pilots must complete thousands of flight hours and pass rigorous examinations before they can fly commercial aircraft carrying hundreds of passengers safely across continents and oceans daily",
        "The talented musician composed an incredibly beautiful symphony that captured the hearts of audiences worldwide and earned numerous prestigious international awards and recognition from critics and peers everywhere",
        "Dedicated researchers work tirelessly in laboratories analyzing complex data to find solutions to some of humanity's most challenging medical problems and develop innovative treatments for serious diseases",
        "The ambitious entrepreneur developed an innovative technology platform that revolutionized the way people communicate and share information globally every day through digital networks and mobile devices worldwide",
        "Professional photographers travel to remote locations around the world to capture stunning images of rare wildlife in their natural undisturbed habitats for conservation awareness and scientific research purposes",
        "The compassionate doctor spent countless hours treating patients suffering from various illnesses and providing emotional support to their worried families during difficult times at the hospital emergency department",
        "Talented dancers spend many years perfecting their technique through daily practice sessions that strengthen their bodies and improve their artistic expression significantly for stage performances and competitions worldwide",
        "The brilliant scientist discovered a groundbreaking method for converting renewable energy sources into electricity more efficiently than ever before imagined which could help solve global energy crisis",
        "Skilled architects design magnificent buildings that combine functionality with aesthetic beauty while considering environmental sustainability and energy efficiency to minimize carbon footprint and protect our precious planet",
        "The dedicated veterinarian treats injured animals with gentle care and performs complicated surgical procedures to save the lives of beloved family pets and restore their health completely",
        "Accomplished writers spend countless hours crafting compelling stories that transport readers to different worlds and evoke powerful emotional responses through vivid descriptions and relatable characters that resonate deeply",
        "The experienced archaeologist carefully excavates ancient artifacts buried for thousands of years to better understand how our ancestors lived their daily lives and developed their unique cultures",
        "Talented artists create breathtaking paintings and sculptures that reflect their unique perspectives and interpretations of the world around them using various mediums techniques and styles throughout art history",
        "The meticulous watchmaker repairs intricate timepieces using specialized tools and demonstrates exceptional patience while working on tiny delicate components that require steady hands and excellent eyesight always",
        "Professional athletes maintain strict training schedules and follow carefully planned nutrition programs to keep their bodies in peak physical condition for competitions and achieve optimal performance results consistently",
        "The brilliant mathematician solved an extremely complex equation that had puzzled scholars and researchers for many decades using innovative mathematical approaches and creative thinking methods never tried before",
        "Dedicated teachers spend countless hours preparing engaging lesson plans and providing individualized attention to help each student reach their full potential and achieve academic success in their studies",
        "The innovative engineer designed an efficient transportation system that reduces traffic congestion and minimizes environmental impact in crowded urban areas improving quality of life for millions of city residents",
        "Skilled craftspeople create beautiful handmade furniture using traditional woodworking techniques passed down through many generations of their families maintaining cultural heritage and artistic traditions over centuries",
        "The passionate environmentalist works tirelessly to protect endangered species and preserve natural habitats threatened by human development and climate change through advocacy education and conservation efforts worldwide",
        "Talented musicians collaborate to create harmonious symphonies that blend different instruments and voices into one cohesive beautiful artistic expression that moves audiences emotionally and showcases collective creativity",
        "The experienced surgeon performs delicate operations with remarkable precision using advanced medical technology and techniques developed through years of practice training and continuous learning in the field",
        "Dedicated social workers help vulnerable individuals and families overcome difficult challenges by connecting them with essential resources and providing emotional support during crisis situations and transitions",
        "The accomplished astronomer discovers new celestial objects in deep space using powerful telescopes and sophisticated computer programs to analyze collected data from distant stars and galaxies billions of light years away",
        "Professional chefs create exquisite culinary masterpieces by combining unique ingredients with innovative cooking techniques and presenting them with artistic flair that delights all senses and creates memorable dining experiences",
        "The brilliant physicist develops groundbreaking theories about the fundamental nature of the universe using complex mathematical models and experimental evidence gathered from particle accelerators and astronomical observations worldwide",
        "Skilled translators convert important documents and literary works from one language to another while preserving the original meaning cultural context and artistic nuances that make communication across cultures possible",
        "The dedicated firefighter risks personal safety to rescue people trapped in burning buildings and provides emergency medical assistance at accident scenes showing incredible bravery and commitment to community service",
        "Talented choreographers create stunning dance performances that tell compelling stories through graceful movements and powerful emotional expressions by dancers who train rigorously to perfect every gesture and step",
        "The innovative software developer creates useful applications that solve real world problems and improve the daily lives of millions of users worldwide through intuitive interfaces and efficient code",
        "Experienced pilots navigate aircraft through challenging weather conditions using advanced instruments and rely on years of training to ensure passenger safety during flights across continents and over vast oceans",
        "The compassionate counselor helps individuals overcome personal struggles by providing guidance encouragement and practical strategies for positive life changes that lead to better mental health and wellbeing overall",
        "Accomplished poets craft beautiful verses that capture complex emotions and universal human experiences using carefully chosen words and rhythmic patterns that resonate with readers across different cultures and time periods",
        "The dedicated marine biologist studies ocean ecosystems to understand how different species interact and develops strategies to protect endangered marine life from threats like pollution and climate change worldwide",
        "Skilled electricians install and repair complex wiring systems in buildings ensuring that electrical power is distributed safely and efficiently throughout all rooms floors and areas without any hazards or malfunctions",
        "The innovative urban planner designs sustainable cities that balance residential commercial and green spaces to create livable communities for future generations while considering environmental impact and resource management",
        "Professional journalists investigate important stories thoroughly and report facts accurately to keep the public informed about significant events and issues affecting society politics economy and culture in their communities",
        "The accomplished violinist performs classical concertos with exceptional technical skill and emotional depth that moves audiences to tears during sold out concerts at prestigious venues and music festivals worldwide",
        "Dedicated paramedics provide critical emergency medical care at accident scenes and transport injured patients safely to hospitals for additional treatment working long shifts to save lives every day",
        "The talented graphic designer creates visually stunning advertisements and brand identities that effectively communicate messages and capture consumer attention in crowded marketplaces using color typography and innovative layouts",
        "Experienced mechanics diagnose and repair complex automotive problems using specialized diagnostic equipment and comprehensive knowledge of vehicle systems accumulated through years of hands on training and practical experience",
        "The passionate historian researches and documents important events from the past using primary sources to provide accurate accounts for future generations ensuring that cultural heritage and lessons are preserved",
        "Skilled carpenters construct beautiful custom furniture pieces using high quality materials and traditional woodworking techniques passed down through generations creating heirloom pieces that last for many decades",
        "The innovative biotechnology researcher develops new medical treatments using cutting edge genetic engineering techniques that could revolutionize healthcare worldwide and provide cures for previously untreatable diseases affecting millions",
        "Professional meteorologists analyze atmospheric data from multiple sources to create accurate weather forecasts that help people plan their daily activities and prepare for severe storms and natural disasters safely",
        "The dedicated librarian helps patrons locate information and resources while maintaining organized collections and creating programs to promote literacy in communities serving diverse populations with varying information needs",
        "Talented cinematographers capture stunning visual sequences using sophisticated camera equipment and lighting techniques to create memorable scenes in films that tell compelling stories and evoke strong emotional responses",
        "The experienced geologist studies rock formations and mineral deposits to understand Earth's geological history and locate valuable natural resources for extraction while considering environmental impact and sustainability issues",
        "Accomplished pianists master extremely difficult musical compositions through countless hours of dedicated practice and perform with remarkable technical precision and artistry at concerts worldwide earning critical acclaim and awards",
        "The innovative aerospace engineer designs advanced spacecraft and propulsion systems that enable humanity to explore distant planets and expand knowledge of the universe through manned and unmanned missions",
        "Professional sommeliers possess encyclopedic knowledge of wines from different regions and expertly pair beverages with cuisine to enhance dining experiences at fine restaurants creating perfect flavor combinations for guests",
        "The dedicated physical therapist helps patients recover from injuries through customized exercise programs and manual therapy techniques that restore mobility and strength allowing them to return to normal activities",
        "Skilled forensic scientists analyze evidence from crime scenes using advanced laboratory techniques and scientific methods to help solve complex criminal investigations and bring justice to victims and their families",
        "The passionate anthropologist studies human cultures and societies throughout history to understand how people adapt to different environments and develop unique traditions customs and belief systems across diverse regions",
        "Accomplished conductors lead orchestras through complex musical performances by coordinating dozens of musicians and interpreting composers' intentions with artistic vision creating unified memorable concerts that inspire audiences worldwide",
        "The innovative agricultural scientist develops new farming techniques and crop varieties that increase food production while reducing environmental impact to help feed the growing global population sustainably",
        "Professional diplomats negotiate international agreements and resolve conflicts between nations through careful diplomacy and communication skills helping to maintain peace and promote cooperation in the global community",
        "The dedicated speech therapist helps children and adults overcome communication disorders through specialized exercises and techniques that improve their ability to express themselves clearly and confidently in various situations",
        "Talented fashion designers create innovative clothing collections that reflect current trends while pushing artistic boundaries using unique fabrics colors and silhouettes that influence the global fashion industry significantly",
        "The experienced oceanographer explores deep sea environments using submersibles and remote sensing technology to discover new species and understand marine ecosystems that cover most of our planet's surface",
        "Skilled opticians craft precision eyewear and contact lenses that correct vision problems and improve quality of life for millions of people worldwide using advanced optical technology and careful measurements",
        "The passionate music teacher inspires young students to develop their musical talents through patient instruction and encouragement helping them discover the joy of creating and performing music for others",
        "Professional editors refine written content for publication ensuring clarity accuracy and proper style while working with authors to improve their work and bring important stories and information to readers",
        "The dedicated conservationist works to protect threatened ecosystems and wildlife habitats through research advocacy and hands on restoration efforts combating deforestation pollution and other environmental threats globally",
        "Talented illustrators create captivating visual art for books magazines and digital media using various techniques and styles that bring stories to life and enhance reader engagement and comprehension",
        "The innovative robotics engineer designs and programs autonomous machines that can perform complex tasks in manufacturing healthcare and exploration expanding the possibilities of human technological achievement dramatically",
        "Professional voice actors bring animated characters and narrations to life through skilled vocal performances that convey emotion personality and meaning using only their voices to create memorable entertainment experiences",
        "The experienced horticulturist cultivates and studies plants developing new varieties and techniques that improve agricultural productivity and enhance the beauty of gardens parks and landscapes in communities worldwide",
        "Skilled midwives provide essential care and support to expectant mothers during pregnancy childbirth and postpartum period combining medical knowledge with compassionate personal attention to ensure healthy outcomes",
        "The passionate art historian analyzes and interprets visual art from different periods and cultures providing context and insights that deepen understanding and appreciation of human creative expression throughout history",
        "Professional sommeliers not only recommend wines but also educate customers about grape varieties regions production methods and proper storage techniques sharing their expertise to enhance appreciation of viticulture",
        "The dedicated emergency dispatcher coordinates responses to crisis situations by gathering critical information from callers and directing appropriate resources working under pressure to help save lives every single day",
        "Talented portrait photographers capture the essence and personality of their subjects through careful composition lighting and timing creating images that preserve memories and tell stories for generations to come",
        "The innovative materials scientist develops new substances with unique properties that enable advances in technology medicine and manufacturing pushing the boundaries of what is physically possible with matter",
        "Professional landscape architects design outdoor spaces that blend functionality aesthetics and environmental sustainability creating parks gardens and public areas that enhance communities and connect people with nature beautifully",
        "The experienced trauma counselor helps individuals process and heal from difficult experiences through evidence based therapeutic techniques providing safe space and professional guidance for recovery and personal growth",
        "Skilled gemologists identify authenticate and appraise precious stones using specialized knowledge and equipment ensuring accurate valuation and helping prevent fraud in the jewelry and investment markets globally",
        "The passionate wildlife photographer documents rare and endangered species in their natural habitats through patient observation and technical skill raising awareness about conservation issues and the beauty of biodiversity",
        "Professional perfumers blend aromatic compounds to create signature fragrances that evoke emotions and memories using their highly trained sense of smell and understanding of chemistry to produce olfactory art",
        "The dedicated neuroscientist investigates the complex workings of the human brain using advanced imaging and research methods seeking to understand consciousness memory and neurological disorders for improved treatments",
        "Talented stunt coordinators design and execute dangerous action sequences in films and television ensuring performer safety while creating thrilling entertainment that captivates audiences worldwide with realistic spectacular feats",
        "The innovative industrial designer creates functional aesthetically pleasing products that improve daily life by considering user needs manufacturing processes and environmental impact in their creative design solutions",
        "Professional genealogists help people discover their family history and ancestry through careful research of historical records documents and genetic data connecting individuals to their roots and cultural heritage",
        "The experienced falconer trains and works with birds of prey using ancient techniques passed down through centuries forming unique bonds with these magnificent creatures for hunting demonstration and conservation purposes",
        "The accomplished documentary filmmaker travels extensively to capture compelling stories from diverse communities around the world presenting authentic perspectives that educate inform and inspire audiences to take meaningful action",
        "Professional sommeliers carefully curate wine selections for prestigious restaurants developing extensive knowledge of vintages regions and varietals to provide expert recommendations that enhance customers' dining experiences significantly every evening",
        "The dedicated marine conservationist works tirelessly to protect fragile coral reef ecosystems from destructive fishing practices and climate change impacts implementing sustainable solutions that preserve biodiversity for future generations worldwide",
        "Accomplished neurosurgeons perform incredibly delicate brain and spinal cord operations using advanced microsurgical techniques and state of the art imaging technology to treat complex neurological conditions and save patients' lives daily",
        "The innovative industrial designer creates functional aesthetically pleasing consumer products that improve daily life by carefully considering ergonomics manufacturing processes sustainability and user experience in every design decision made",
        "Professional cryptographers develop sophisticated encryption algorithms to secure sensitive digital communications and protect private information from unauthorized access in an increasingly interconnected world where cyber security threats constantly evolve",
        "The experienced trauma surgeon treats critically injured patients in busy emergency departments making split second life saving decisions under enormous pressure while coordinating with multidisciplinary medical teams twenty four hours every day",
        "Talented special effects artists create breathtaking visual sequences for blockbuster films using cutting edge computer graphics technology blending practical effects with digital elements to produce stunning imagery that captivates global audiences",
        "The dedicated environmental engineer designs innovative systems to treat contaminated water and air reduce industrial pollution and minimize ecological impact helping communities access clean safe resources essential for health and wellbeing",
        "Professional mountain guides lead challenging expeditions to remote peaks around the world ensuring climbers' safety through careful route planning risk assessment and expert knowledge of high altitude conditions and emergency procedures always",
        "The accomplished ornithologist studies rare bird species in their natural habitats documenting migration patterns breeding behaviors and population dynamics to support conservation efforts protecting endangered avian wildlife from extinction threats worldwide",
        "Skilled violin makers handcraft magnificent instruments using traditional techniques passed down through centuries selecting premium aged wood and applying numerous layers of varnish to produce exceptional tonal quality and beautiful aesthetics",
        "The innovative geneticist researches complex hereditary diseases analyzing DNA sequences to identify mutations and develop targeted gene therapies that could revolutionize medical treatment and improve outcomes for millions of patients globally",
        "Professional wine makers carefully oversee every stage of production from harvesting grapes at optimal ripeness through fermentation and aging processes creating distinctive vintages that reflect unique terroir and showcase exceptional craftsmanship annually",
        "The dedicated pediatric oncologist treats children battling cancer with compassionate care advanced chemotherapy protocols and innovative immunotherapy approaches while providing emotional support to worried families during extremely difficult challenging times",
        "Accomplished screenwriters craft compelling narratives for television and film developing complex characters and engaging plot lines through countless revisions and collaborations with directors and producers to create entertaining stories audiences worldwide love",
        "The experienced seismologist monitors earthquake activity using sensitive instruments and analyzes geological data to better understand tectonic plate movements providing early warning systems that protect communities from devastating natural disasters globally",
        "Professional air traffic controllers manage the safe efficient movement of aircraft through busy airspace coordinating thousands of flights daily while maintaining constant vigilance and making critical decisions that ensure passenger safety always",
        "The talented pastry chef creates exquisite desserts combining artistic presentation with exceptional flavors using premium ingredients classical French techniques and innovative modern approaches to delight restaurant guests with memorable sweet endings",
        "Dedicated humanitarian workers provide essential aid to vulnerable populations affected by wars natural disasters and poverty delivering food medical care and education in extremely challenging dangerous conditions to help communities rebuild lives",
        "The accomplished quantum physicist investigates the fundamental nature of reality at subatomic scales conducting experiments with particle accelerators to test theoretical predictions and advance human understanding of the universe's most mysterious phenomena",
        "Professional restoration experts carefully preserve and repair priceless historical artifacts and artworks using specialized techniques and materials ensuring cultural treasures survive for future generations to appreciate study and enjoy worldwide",
        "The innovative app developer creates useful mobile applications that solve real world problems streamline daily tasks and connect people across distances using intuitive user interfaces and efficient programming to enhance modern digital lifestyles",
        "Experienced avalanche forecasters assess dangerous snow conditions in mountainous regions analyzing weather patterns terrain features and snowpack stability to issue accurate warnings that prevent tragedies and save outdoor enthusiasts' lives regularly",
        "The accomplished textile designer creates beautiful original fabric patterns using color theory artistic vision and technical knowledge of weaving and printing processes producing unique materials for fashion houses and interior decorators worldwide",
        "Professional paleoclimatologists study ancient climate patterns by analyzing ice cores sediment layers and fossil records to understand long term environmental changes and provide crucial data for predicting future global warming impacts accurately",
        "The dedicated wildlife rehabilitator cares for injured orphaned animals with expertise and compassion treating medical conditions and teaching survival skills before safely releasing recovered creatures back into their natural habitats successfully",
        "Accomplished sound engineers record mix and master audio for music albums films and live performances using sophisticated equipment and trained ears to create perfectly balanced sonic experiences that move audiences emotionally worldwide",
        "The innovative biomedical engineer designs artificial organs prosthetic limbs and medical devices that restore function and improve quality of life for patients with disabilities and chronic conditions using advanced materials and technologies",
        "Professional volcano logists monitor active volcanoes around the world studying eruption patterns lava flows and seismic activity to predict dangerous events and protect nearby communities from catastrophic disasters through timely evacuations always",
        "The talented ballroom dancer performs elegant routines with incredible precision and grace having trained intensively for many years to master complex footwork timing and partnering skills for competitions and professional shows worldwide",
        "Dedicated search and rescue teams respond to emergencies in remote wilderness areas using specialized training equipment and determination to locate missing persons often working through harsh weather conditions to save lives courageously",
        "The accomplished lexicographer compiles comprehensive dictionaries by researching word origins meanings and usage patterns across different time periods and regions providing authoritative references that preserve and document evolving languages accurately",
        "Professional storm chasers track severe weather systems across vast distances documenting tornadoes hurricanes and thunderstorms with sophisticated equipment to advance meteorological science and improve forecasting capabilities that protect communities effectively",
        "The innovative prosthetics specialist designs and fits custom artificial limbs using cutting edge materials and technologies helping amputees regain mobility independence and confidence to pursue active fulfilling lives without limitations successfully",
        "Experienced ecologists study complex relationships between organisms and their environments conducting field research to understand biodiversity ecosystem health and environmental impacts informing conservation strategies that protect natural habitats worldwide",
        "The accomplished synchronized swimming team performs intricate choreographed routines with perfect timing and athleticism having practiced countless hours to achieve seamless coordination underwater and artistic expression that amazes audiences",
        "Professional antique appraisers evaluate valuable historical objects using expert knowledge of periods styles and makers to determine authentic ity and fair market value helping collectors museums and estates manage precious heirlooms responsibly",
        "The dedicated dialysis nurse provides critical care to patients with kidney failure operating complex machines monitoring vital signs and offering emotional support during lengthy treatments that sustain life and maintain health regularly",
        "Talented ice sculptors transform massive frozen blocks into breathtaking artistic creations using chainsaws chisels and creative vision to produce intricate detailed works for weddings corporate events and competitions worldwide before they melt",
        "The innovative nuclear engineer designs safer more efficient reactors and develops advanced technologies for clean energy production radioactive waste management and medical applications that benefit society while minimizing environmental risks globally",
        "Professional cave explorers venture deep underground discovering new passages geological formations and ancient ecosystems while carefully documenting findings and practicing responsible conservation to preserve these unique fragile environments for future research",
        "The accomplished horticulturist cultivates rare exotic plant species in botanical gardens using specialized knowledge of soil conditions climate requirements and propagation techniques to preserve biodiversity and educate the public about plant conservation",
        "Dedicated midwives provide compassionate care to pregnant women throughout labor and delivery using clinical expertise and emotional support to ensure safe healthy births while respecting cultural traditions and family wishes in diverse communities",
        "The talented glassblower creates stunning functional and decorative pieces by heating shaping and cooling molten glass using traditional furnaces and tools passed down through generations producing unique artwork prized by collectors worldwide",
        "Professional cryptozoologists investigate reports of undiscovered mysterious creatures conducting field research in remote locations analyzing evidence and interviewing witnesses to determine whether legendary animals might actually exist in hidden habitats",
        "The innovative tissue engineer grows replacement organs and body parts in laboratories using stem cells and scaffolding materials developing revolutionary medical treatments that could eliminate transplant waiting lists and save countless lives",
        "Experienced wilderness survival instructors teach essential skills for thriving in remote outdoor environments including fire starting shelter building food procurement and navigation using natural resources helping adventurers prepare for emergency situations confidently",
        "The accomplished falconry demonstrates the ancient art of hunting with trained birds of prey performing educational shows that showcase the incredible speed agility and intelligence of raptors while promoting wildlife conservation awareness globally"
    ]
    
    # Select sentences based on difficulty
    if actual_difficulty == "easy":
        sentence_pool = all_easy_sentences
    elif actual_difficulty == "medium":
        sentence_pool = all_medium_sentences
    else:  # hard
        sentence_pool = all_hard_sentences
    
    # Return a random sentence from the pool
    import random
    return random.choice(sentence_pool)

def generate_spell_word(difficulty="easy", user_level=1):
    """Generate words with variety - respects user's difficulty choice"""
    
    # Use the difficulty selected by the user directly
    actual_difficulty = difficulty
    
    # SPELL BEE WORD POOLS: 150 words per difficulty level (Alphabetical Order)
    word_pools = {
        "easy": [
            # 150 Easy words - Alphabetical Order
            "baby", "bag", "ball", "bed", "bell", "bird", "blanket", "blue", "boat", "book",
            "box", "bread", "brush", "bus", "cake", "cap", "car", "chair", "city", "class",
            "clean", "clock", "cloud", "coat", "cold", "comb", "cup", "dark", "day", "desk",
            "dog", "door", "drink", "ear", "east", "eat", "egg", "eye", "fan", "farm",
            "fast", "fish", "flower", "foot", "fork", "friend", "fruit", "garden", "glass", "grass",
            "green", "hand", "happy", "hat", "hill", "home", "hot", "jump", "key", "king",
            "knife", "lake", "laugh", "leaf", "light", "lock", "map", "milk", "mirror", "month",
            "moon", "night", "north", "nose", "park", "pen", "phone", "photo", "pink", "pillow",
            "plane", "plate", "play", "queen", "rain", "raincoat", "read", "red", "rice", "ring",
            "river", "road", "run", "sad", "salt", "sand", "school", "sea", "seed", "shirt",
            "ship", "shoe", "shop", "short", "sing", "sky", "slow", "small", "smile", "soap",
            "sock", "south", "spoon", "stand", "star", "sugar", "sun", "sweet", "table", "tall",
            "thunder", "time", "town", "toy", "train", "tree", "wall", "watch", "week", "west",
            "wind", "write", "year"
        ],
        "medium": [
            # 150 Medium words - Alphabetical Order
            "abandon", "absorb", "abstract", "abundant", "accurate", "acquire", "adjacent", "adjust", "admire", "advanced",
            "advocate", "allocate", "alternative", "ambitious", "analysis", "anticipate", "apparent", "appropriate", "argument", "arrangement",
            "artificial", "assistance", "assume", "attempt", "attractive", "awareness", "beneficial", "boundary", "calculate", "capacity",
            "celebrate", "circumstance", "collaborate", "combine", "communicate", "community", "compare", "compatible", "compensate", "competitive",
            "concentrate", "conclude", "conduct", "confirm", "connect", "conscious", "consider", "consistent", "construct", "consume",
            "contribute", "convenient", "convert", "cooperate", "coordinate", "corporate", "creative", "critical", "dedicate", "demonstrate",
            "depend", "detect", "determine", "diagnose", "distribute", "domestic", "efficient", "elaborate", "eliminate", "emphasize",
            "encounter", "encourage", "enormous", "essential", "evaluate", "evident", "examine", "exceed", "exclude", "expand",
            "expert", "flexible", "formulate", "frequent", "generate", "genuine", "graduate", "illustrate", "immediate", "implement",
            "implication", "incorporate", "indicate", "individual", "inevitable", "initial", "innovate", "inspire", "integrate", "intelligent",
            "interact", "internal", "interpret", "interrupt", "invest", "isolate", "justify", "maintain", "majority", "maximum",
            "mechanism", "motivate", "negotiate", "observe", "obtain", "participate", "perceive", "perspective", "potential", "precise",
            "predict", "preference", "priority", "procedure", "profession", "proficient", "prohibit", "promote", "pursue", "rational",
            "recognize", "recommend", "reflect", "regulate", "reinforce", "relevant", "require", "research", "resolve", "restrict",
            "significant", "strategy", "sufficient", "supervise", "sustainable", "technical", "temporary", "transform", "transmit", "universal", "utilize"
        ],
        "hard": [
            # 150 Hard words - Alphabetical Order (Very Difficult)
            "aberration", "abnegation", "abstemious", "acquiesce", "acrimonious", "adumbrate", "alacrity", "amalgamation", "anachronism", "antipathy",
            "apocryphal", "approbation", "arbitrary", "ascetic", "assiduous", "audacious", "belligerent", "benevolent", "bombastic", "cacophony",
            "capricious", "catharsis", "caustic", "clandestine", "cogent", "commensurate", "complacent", "conundrum", "copious", "corpulent",
            "deleterious", "demagogue", "derelict", "despot", "didactic", "dissonance", "eclectic", "effervescent", "egregious", "eloquent",
            "enigmatic", "ephemeral", "equivocal", "esoteric", "euphemism", "exacerbate", "exasperate", "exculpate", "exuberant", "facetious",
            "fastidious", "felicity", "fortuitous", "garrulous", "gratuitous", "grandiloquent", "haphazard", "harangue", "hegemony", "idiosyncrasy",
            "impassive", "impetuous", "implacable", "incognito", "indefatigable", "indolent", "ineffable", "ingenuous", "insidious", "insipid",
            "intrepid", "irascible", "juxtapose", "labyrinthine", "laconic", "loquacious", "magnanimous", "malevolent", "meticulous", "mollify",
            "munificent", "nefarious", "nonchalant", "obdurate", "obfuscate", "obsequious", "obstreperous", "panacea", "parsimonious", "pejorative",
            "pernicious", "perfidious", "perspicacious", "petulant", "plethora", "pragmatic", "precocious", "proclivity", "prodigious", "querulous",
            "quixotic", "rancorous", "recalcitrant", "recondite", "reprehensible", "sagacious", "sanctimonious", "scrupulous", "serendipity", "soliloquy",
            "spurious", "taciturn", "tenacious", "trepidation", "truculent", "ubiquitous", "unassailable", "unctuous", "vacillate", "vehement",
            "verbose", "vicarious", "vindicate", "vitriolic", "vociferous", "whimsical", "winsome", "xenophobia", "zealous", "zeppelin"
        ]
    }
    
    word_list = word_pools.get(actual_difficulty, word_pools["easy"])
    word = random.choice(word_list)
    
    return word.lower()

def get_word_sentence_usage(word):
    """Generate varied example sentences"""
    
    sentence_patterns = [
        f"Use the word in a sentence about daily life",
        f"Create a sentence showing what this word means",
        f"Make a simple example using this word",
        f"Show how children would use this word",
        f"Give a clear example with this word"
    ]
    
    pattern = random.choice(sentence_patterns)

    prompt = f"""Create ONE simple example sentence using the word "{word}".

{pattern}

RULES:
1. Sentence must be simple for children aged 6-15
2. Clearly show the word's meaning
3. Use simple vocabulary
4. Make it relatable to children
5. Be creative and varied
6. Return ONLY the sentence - no quotes
7. Use different sentence structures
8. Vary tenses

Now create a NEW, DIFFERENT sentence using "{word}"."""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=50
    )

    sentence = response.choices[0].message.content.strip()
    sentence = re.sub(r'^["\']+|["\']+$', '', sentence)
   
    return sentence

def get_word_meaning(word):
    """Enhanced function to explain ANY word - from simple to very complex"""
    
    prompt = f"""You are a helpful English teacher explaining the meaning of "{word}" to students aged 6-15.

CRITICAL INSTRUCTION: You MUST be able to explain ANY word - whether it's simple like "cat" or extremely complex like "perspicacious", "ubiquitous", "aberration", or "ephemeral".

FORMAT YOUR RESPONSE EXACTLY AS:
MEANING: <clear definition using simple language>
EXAMPLE: <a relatable sentence using the word>
TYPE: <noun/verb/adjective/adverb/etc>
TIP: <a helpful memory trick or tip>

RULES - ADAPT TO THE WORD:

For SIMPLE words (cat, run, happy):
- Keep explanation brief and straightforward
- Use everyday examples
- 1-2 sentences is enough

For COMPLEX words (ubiquitous, aberration, acrimonious):
- Break down the meaning into simple parts
- Use analogies or simpler synonyms first
- Explain what it means in everyday situations
- Give context that kids can understand
- Make it memorable with a trick or story

For VERY DIFFICULT words (perspicacious, obfuscate, magnanimous):
- Start with the simplest possible explanation
- Use phrases like "imagine..." or "think of it like..."
- Connect to things students already know
- Make it fun and interesting!

IMPORTANT: 
- Never say "I don't know" or "This word is too hard"
- Always provide a complete explanation
- Make examples relatable to children's lives
- Use encouraging language

Word to explain: "{word}"

Now provide the complete explanation:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,  # Higher for creative explanations of complex words
            max_tokens=500    # More room for detailed explanations
        )
        
        result = response.choices[0].message.content.strip()
        
        # Verify we got a proper response
        if len(result) < 20 or "MEANING:" not in result:
            raise Exception("Invalid AI response")
            
        return result
    
    except Exception as e:
        # Robust fallback if AI fails
        print(f"Error getting meaning for '{word}': {str(e)}")
        return f"""MEANING: {word.capitalize()} is an English word. It has a specific meaning in the English language.
EXAMPLE: This is how you might use the word {word} in a sentence.
TYPE: word
TIP: If you want to learn more about '{word}', try looking it up in a dictionary or asking your teacher for help!"""

def compare_words(student_text, correct_text):
    student_words = student_text.lower().split()
    correct_words = correct_text.lower().split()
    comparison = []
    
    for i, correct_word in enumerate(correct_words):
        if i < len(student_words):
            student_word = student_words[i]
            similarity = SequenceMatcher(None, student_word, correct_word).ratio()
            
            if similarity >= 0.8:
                comparison.append({"word": correct_word, "status": "correct"})
            else:
                comparison.append({"word": correct_word, "status": "incorrect", "spoken": student_word})
        else:
            comparison.append({"word": correct_word, "status": "missing"})
    
    return comparison

def compare_spelling(student_spelling, correct_word):
    student = student_spelling.lower().strip()
    correct = correct_word.lower().strip()
    comparison = []
    max_len = max(len(student), len(correct))
    
    for i in range(max_len):
        if i < len(correct):
            correct_letter = correct[i]
            if i < len(student):
                student_letter = student[i]
                if student_letter == correct_letter:
                    comparison.append({"letter": correct_letter, "status": "correct"})
                else:
                    comparison.append({"letter": correct_letter, "status": "incorrect", "typed": student_letter})
            else:
                comparison.append({"letter": correct_letter, "status": "missing"})
    
    return comparison

# ================= ROUTES =================
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/user-type")
def user_type():
    """Page to select user type (student or teacher)"""
    return render_template("user_type.html")

@app.route("/login", methods=["GET"])
def login_page():
    user_type = request.args.get("type", "student")
    return render_template("login.html", user_type=user_type)

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user_id = data.get("user_id")
    password = data.get("password")
    user_type = data.get("user_type", "student")
    
    if user_type == "teacher":
        # Teacher login
        if user_id in teachers_db:
            if teachers_db[user_id]['password'] == password:
                session['user_id'] = user_id
                session['role'] = 'teacher'
                return jsonify({"success": True, "redirect": "/teacher-dashboard"})
            else:
                return jsonify({"success": False, "message": "Incorrect password."})
        else:
            return jsonify({"success": False, "message": "Teacher username not found."})
    else:
        # Student login
        if user_id and password:
            if user_id in users_db:
                if users_db[user_id]['password'] == password:
                    session['user_id'] = user_id
                    session['role'] = 'student'
                    # Update last active on login
                    users_db[user_id]['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_database()
                    return jsonify({"success": True, "redirect": "/main"})
                else:
                    return jsonify({"success": False, "message": "Incorrect password."})
            else:
                return jsonify({"success": False, "message": "User ID not found. Please sign up first."})
        else:
            return jsonify({"success": False, "message": "Please enter both User ID and Password."})

@app.route("/signup", methods=["GET"])
def signup_page():
    user_type = request.args.get("type", "student")
    return render_template("signup.html", user_type=user_type)

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    user_type = data.get("user_type", "student")
    
    if user_type == "teacher":
        # Teacher signup
        username = data.get("username")
        password = data.get("password")
        name = data.get("name")
        
        if username and password and name:
            if len(username) == 6 and len(password) == 6:
                # Check if username already exists
                if username in teachers_db:
                    return jsonify({"success": False, "message": "Username already exists. Please choose another."})
                else:
                    teachers_db[username] = {
                        "password": password,
                        "name": name,
                        "role": "teacher",
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_database()
                    session['user_id'] = username
                    session['role'] = 'teacher'
                    return jsonify({"success": True, "redirect": "/teacher-dashboard"})
            else:
                return jsonify({"success": False, "message": "Username and Password must be exactly 6 characters each."})
        else:
            return jsonify({"success": False, "message": "Please fill in all fields."})
    else:
        # Student signup
        user_id = data.get("user_id")
        password = data.get("password")
        name = data.get("name")
        student_class = data.get("class")
        division = data.get("division")
        
        if user_id and password and name and student_class and division:
            if len(user_id) == 4 and user_id.isdigit():  # UPDATED: Changed from 3 to 4
                if user_id in users_db:
                    return jsonify({"success": False, "message": "User ID already exists. Please login or choose a different ID."})
                else:
                    users_db[user_id] = {
                        "password": password,
                        "name": name,
                        "class": student_class,
                        "division": division,
                        "total_xp": 0,
                        "total_stars": 0,
                        "level": 1,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "mode_stats": {}
                    }
                    save_database()  # Save immediately after signup
                    session['user_id'] = user_id
                    session['role'] = 'student'
                    return jsonify({"success": True, "redirect": "/main"})
            else:
                return jsonify({"success": False, "message": "User ID must be exactly 4 digits."})  # UPDATED: Changed message
        else:
            return jsonify({"success": False, "message": "Please fill in all fields."})

@app.route("/main")
def main():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    user_data = users_db.get(user_id, {})
    
    recommended_difficulty = get_difficulty_for_level(user_data.get('level', 1))
    
    current_level = user_data.get('level', 1)
    current_xp = user_data.get('total_xp', 0)
    xp_for_current_level = get_xp_for_level(current_level)
    xp_for_next_level = get_xp_for_level(current_level + 1)
    xp_in_current_level = current_xp - xp_for_current_level
    xp_needed_for_next = xp_for_next_level - xp_for_current_level
    
    return render_template("main.html", 
                         user_id=user_id, 
                         user_data=user_data,
                         recommended_difficulty=recommended_difficulty,
                         xp_in_current_level=xp_in_current_level,
                         xp_needed_for_next=xp_needed_for_next)

@app.route("/profile")
def profile():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    user_data = users_db.get(user_id, {})
    
    current_level = user_data.get('level', 1)
    current_xp = user_data.get('total_xp', 0)
    xp_for_current_level = get_xp_for_level(current_level)
    xp_for_next_level = get_xp_for_level(current_level + 1)
    xp_in_current_level = current_xp - xp_for_current_level
    xp_needed_for_next = xp_for_next_level - xp_for_current_level
    
    return render_template("profile.html",
                         user_id=user_id,
                         user_data=user_data,
                         xp_in_current_level=xp_in_current_level,
                         xp_needed_for_next=xp_needed_for_next)

@app.route("/teacher-dashboard")
def teacher_dashboard():
    if 'user_id' not in session or session.get('role') != 'teacher':
        return redirect(url_for('home'))
    
    # Get all unique classes and divisions
    all_classes = set()
    all_divisions = set()
    
    for user_id, user_data in users_db.items():
        all_classes.add(user_data['class'])
        all_divisions.add(user_data['division'])
    
    all_classes = sorted(list(all_classes), key=lambda x: int(x))
    all_divisions = sorted(list(all_divisions))
    
    teacher_name = teachers_db[session['user_id']]['name']
    
    return render_template("teacher_dashboard.html",
                         teacher_name=teacher_name,
                         all_classes=all_classes,
                         all_divisions=all_divisions)

@app.route("/get_class_students", methods=["POST"])
def get_class_students():
    """API endpoint to get students for a specific class and division"""
    if 'user_id' not in session or session.get('role') != 'teacher':
        return jsonify({"success": False, "message": "Unauthorized"})
    
    data = request.json
    selected_class = data.get("class")
    selected_division = data.get("division")
    
    students = []
    for user_id, user_data in users_db.items():
        if user_data['class'] == selected_class and user_data['division'] == selected_division:
            students.append({
                'user_id': user_id,
                'name': user_data['name'],
                'level': user_data['level'],
                'total_xp': user_data['total_xp'],
                'total_stars': user_data['total_stars'],
                'last_active': user_data['last_active']
            })
    
    # Sort by total XP (highest first)
    students.sort(key=lambda x: x['total_xp'], reverse=True)
    
    return jsonify({
        "success": True,
        "students": students,
        "total_students": len(students)
    })

@app.route("/logout")
def logout():
    user_id = session.get('user_id')
    role = session.get('role')
    
    # UPDATED: Save progress before logout
    if role == 'student' and user_id in users_db:
        users_db[user_id]['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_database()  # Explicitly save to JSON
    
    # Clear user's conversation context on logout
    if user_id and user_id in conversation_contexts:
        del conversation_contexts[user_id]
    
    session.pop('user_id', None)
    session.pop('role', None)
    return redirect(url_for('home'))

@app.route("/get_user_stats", methods=["GET"])
def get_user_stats():
    if 'user_id' not in session or session.get('role') != 'student':
        return jsonify({"success": False, "message": "Not logged in"})
    
    user_id = session['user_id']
    user_data = users_db.get(user_id, {})
    
    current_level = user_data.get('level', 1)
    current_xp = user_data.get('total_xp', 0)
    xp_for_current_level = get_xp_for_level(current_level)
    xp_for_next_level = get_xp_for_level(current_level + 1)
    xp_in_current_level = current_xp - xp_for_current_level
    xp_needed_for_next = xp_for_next_level - xp_for_current_level
    
    return jsonify({
        "success": True,
        "total_xp": user_data.get('total_xp', 0),
        "total_stars": user_data.get('total_stars', 0),
        "level": current_level,
        "xp_in_current_level": xp_in_current_level,
        "xp_needed_for_next": xp_needed_for_next,
        "recommended_difficulty": get_difficulty_for_level(current_level)
    })

# ---------- CONVERSATION & ROLEPLAY ----------
@app.route("/process", methods=["POST"])
def process():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    user_text = data["text"]
    roleplay = data.get("roleplay")
    user_id = session['user_id']

    if roleplay:
        ai_reply = roleplay_coach(user_text, roleplay, user_id)
    else:
        ai_reply = english_coach(user_text, user_id)

    correct = praise = question = ""
    for line in ai_reply.split("\n"):
        if line.startswith("CORRECT:"):
            correct = line.replace("CORRECT:", "").strip()
        elif line.startswith("PRAISE:"):
            praise = line.replace("PRAISE:", "").strip()
        elif line.startswith("QUESTION:"):
            question = line.replace("QUESTION:", "").strip()

    final_text = f"{correct}. {praise} {question}"
    audio = speak_to_file(final_text)

    return jsonify({
        "reply": final_text,
        "audio": audio
    })

# ---------- REPEAT AFTER ME ----------
@app.route("/repeat_sentence", methods=["POST"])
def repeat_sentence():
    data = request.json
    category = data.get("category", "general")
    difficulty = data.get("difficulty", "easy")
    
    user_level = 1
    if 'user_id' in session:
        user_data = users_db.get(session['user_id'], {})
        user_level = user_data.get('level', 1)
   
    sentence = generate_repeat_sentence(category, difficulty, user_level)
    audio_normal = speak_to_file(sentence, slow=False)
    audio_slow = speak_to_file(sentence, slow=True)

    return jsonify({
        "sentence": sentence,
        "audio": audio_normal,
        "audio_slow": audio_slow
    })

@app.route("/check_repeat", methods=["POST"])
def check_repeat():
    data = request.json
    student = data["student"]
    correct = data["correct"]
    stage_complete = data.get("stage_complete", False)
    accumulated_stars = data.get("accumulated_stars", 0)  # Stars from previous questions

    score = SequenceMatcher(None, student.lower(), correct.lower()).ratio()
    word_comparison = compare_words(student, correct)

    if score >= 0.9:
        feedback = "Perfect! Amazing pronunciation!"
        stars = 3
    elif score >= 0.75:
        feedback = "Great job! Keep practicing!"
        stars = 2
    elif score >= 0.6:
        feedback = "Good try! Try speaking more clearly."
        stars = 1
    else:
        feedback = "Keep trying! Speak slowly and clearly."
        stars = 0

    # Only save progress if stage is complete (5 sentences done)
    level_info = None
    if stage_complete and 'user_id' in session:
        # Save total stars (accumulated + current question)
        total_stars_earned = accumulated_stars + stars
        level_info = save_user_progress(session['user_id'], total_stars_earned, 'repeat')

    return jsonify({
        "feedback": feedback,
        "score": round(score * 100),
        "stars": stars,
        "word_comparison": word_comparison,
        "level_info": level_info,
        "stars_saved": stage_complete
    })

# ---------- SPELL BEE ----------
@app.route("/spell_word", methods=["POST"])
def spell_word():
    data = request.json
    difficulty = data.get("difficulty", "easy")
    
    user_level = 1
    if 'user_id' in session:
        user_data = users_db.get(session['user_id'], {})
        user_level = user_data.get('level', 1)
   
    word = generate_spell_word(difficulty, user_level)
    usage = get_word_sentence_usage(word)
   
    audio_word = speak_to_file(word, slow=True)
    audio_sentence = speak_to_file(usage, slow=False)
   
    return jsonify({
        "word": word,
        "usage": usage,
        "audio_word": audio_word,
        "audio_sentence": audio_sentence
    })

@app.route("/check_spelling", methods=["POST"])
def check_spelling():
    data = request.json
    student_spelling = data["spelling"]
    correct_word = data["correct"]
    stage_complete = data.get("stage_complete", False)
    accumulated_stars = data.get("accumulated_stars", 0)  # Stars from previous questions
   
    student = student_spelling.lower().strip()
    correct = correct_word.lower().strip()
   
    is_correct = (student == correct)
    letter_comparison = compare_spelling(student, correct)
   
    if is_correct:
        feedback = "🎉 Perfect! You spelled it correctly!"
        stars = 3
    else:
        similarity = SequenceMatcher(None, student, correct).ratio()
        if similarity >= 0.8:
            feedback = "Almost there! Check a few letters."
            stars = 2
        elif similarity >= 0.5:
            feedback = "Good try! Keep practicing!"
            stars = 1
        else:
            feedback = "Try again! Listen carefully to the word."
            stars = 0
    
    # Only save progress if stage is complete (5 words done)
    level_info = None
    if stage_complete and 'user_id' in session:
        # Save total stars (accumulated + current question)
        total_stars_earned = accumulated_stars + stars
        level_info = save_user_progress(session['user_id'], total_stars_earned, 'spellbee')
   
    return jsonify({
        "correct": is_correct,
        "feedback": feedback,
        "stars": stars,
        "letter_comparison": letter_comparison,
        "correct_spelling": correct,
        "level_info": level_info,
        "stars_saved": stage_complete
    })

# ---------- WORD MEANINGS ----------
@app.route("/get_meaning", methods=["POST"])
def get_meaning():
    """Enhanced route with error handling for ANY word lookup"""
    try:
        data = request.json
        word = data.get("word", "").strip()
        
        # Validate input
        if not word:
            return jsonify({
                "error": "No word provided",
                "word": "",
                "meaning": "Please enter a word to get its meaning.",
                "usage": "",
                "type": "",
                "tip": "",
                "audio": None
            }), 400
        
        # Get meaning from AI
        meaning_response = get_word_meaning(word)
       
        # Parse AI response
        meaning = usage = word_type = tip = ""
        for line in meaning_response.split("\n"):
            if line.startswith("MEANING:"):
                meaning = line.replace("MEANING:", "").strip()
            elif line.startswith("EXAMPLE:"):
                usage = line.replace("EXAMPLE:", "").strip()
            elif line.startswith("TYPE:"):
                word_type = line.replace("TYPE:", "").strip()
            elif line.startswith("TIP:"):
                tip = line.replace("TIP:", "").strip()
        
        # Fallback defaults if parsing failed
        if not meaning:
            meaning = f"The word '{word}' has a specific meaning in English."
        if not usage:
            usage = f"Here's an example: The word {word} can be used in sentences."
        if not word_type:
            word_type = "word"
        if not tip:
            tip = "Keep learning new words every day to improve your vocabulary!"
       
        # Generate audio
        audio_text = f"{word}. {meaning}. For example: {usage}. {tip}"
        audio = speak_to_file(audio_text, slow=False)
       
        return jsonify({
            "word": word,
            "meaning": meaning,
            "usage": usage,
            "type": word_type,
            "tip": tip,
            "audio": audio
        })
    
    except Exception as e:
        # Error logging and graceful fallback
        print(f"Error in get_meaning route: {str(e)}")
        word_safe = word if 'word' in locals() else "unknown"
        
        return jsonify({
            "word": word_safe,
            "meaning": f"I'm having trouble explaining '{word_safe}' right now.",
            "usage": "Please try again in a moment, or ask your teacher for help.",
            "type": "word",
            "tip": "Don't worry! You can always look up words in a dictionary too!",
            "audio": None
        }), 200  # Return 200 to avoid breaking the UI

if __name__ == "__main__":
    app.run(debug=True)