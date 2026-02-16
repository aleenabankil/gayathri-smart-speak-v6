#!/usr/bin/env python3
"""
MongoDB Database Module for Gayathri Smart Speak
Handles all database operations for users, teachers, and conversations
"""

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import os
from datetime import datetime

# MongoDB connection
MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')

if not MONGO_URI:
    print("⚠️ WARNING: No MongoDB URI found in environment variables!")
    print("Using fallback local MongoDB (data will not persist)")
    MONGO_URI = 'mongodb://localhost:27017/'

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test connection
    client.admin.command('ping')
    db = client['gayathri_smart_speak']
    users_collection = db['users']
    teachers_collection = db['teachers']
    conversations_collection = db['conversations']
    print("✅ MongoDB connected successfully!")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    print("App will continue but data will NOT persist!")
    client = None
    db = None
    users_collection = None
    teachers_collection = None
    conversations_collection = None

# ==================== USER FUNCTIONS ====================

def create_user(user_id, username, password, user_type='student'):
    """Create a new user in the database"""
    if users_collection is None:
        return None
    
    try:
        user = {
            '_id': user_id,
            'username': username,
            'password': password,
            'user_type': user_type,
            'total_xp': 0,
            'total_stars': 0,
            'level': 1,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_active': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'mode_stats': {},
            'achievements': []
        }
        users_collection.insert_one(user)
        print(f"✅ User created: {username} ({user_id})")
        return user
    except DuplicateKeyError:
        print(f"⚠️ User already exists: {user_id}")
        return None
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return None

def get_user_by_username(username):
    """Get user by username"""
    if users_collection is None:
        return None
    
    try:
        return users_collection.find_one({'username': username})
    except Exception as e:
        print(f"❌ Error getting user by username: {e}")
        return None

def get_user_by_id(user_id):
    """Get user by ID"""
    if users_collection is None:
        return None
    
    try:
        return users_collection.find_one({'_id': user_id})
    except Exception as e:
        print(f"❌ Error getting user by ID: {e}")
        return None

def update_user(user_id, update_data):
    """Update user data"""
    if users_collection is None:
        return False
    
    try:
        # Always update last_active
        update_data['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = users_collection.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        print(f"❌ Error updating user: {e}")
        return False

def update_user_xp(user_id, xp, level, stars=None):
    """Update user XP, level, and optionally stars"""
    if users_collection is None:
        return False
    
    try:
        update_data = {
            'total_xp': xp,
            'level': level,
            'last_active': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if stars is not None:
            update_data['total_stars'] = stars
        
        result = users_collection.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        print(f"❌ Error updating user XP: {e}")
        return False

def update_user_mode_stats(user_id, mode, stars_earned):
    """Update user mode-specific statistics"""
    if users_collection is None:
        return False
    
    try:
        result = users_collection.update_one(
            {'_id': user_id},
            {
                '$inc': {
                    f'mode_stats.{mode}.stars': stars_earned,
                    f'mode_stats.{mode}.sessions': 1
                },
                '$set': {
                    'last_active': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            },
            upsert=True
        )
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        print(f"❌ Error updating mode stats: {e}")
        return False

def get_all_users():
    """Get all users (for teacher dashboard)"""
    if users_collection is None:
        return []
    
    try:
        return list(users_collection.find({'user_type': 'student'}))
    except Exception as e:
        print(f"❌ Error getting all users: {e}")
        return []

# ==================== TEACHER FUNCTIONS ====================

def create_teacher(teacher_id, username, password):
    """Create a new teacher in the database"""
    if teachers_collection is None:
        return None
    
    try:
        teacher = {
            '_id': teacher_id,
            'username': username,
            'password': password,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_active': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        teachers_collection.insert_one(teacher)
        print(f"✅ Teacher created: {username} ({teacher_id})")
        return teacher
    except DuplicateKeyError:
        print(f"⚠️ Teacher already exists: {teacher_id}")
        return None
    except Exception as e:
        print(f"❌ Error creating teacher: {e}")
        return None

def get_teacher_by_username(username):
    """Get teacher by username"""
    if teachers_collection is None:
        return None
    
    try:
        return teachers_collection.find_one({'username': username})
    except Exception as e:
        print(f"❌ Error getting teacher by username: {e}")
        return None

def get_teacher_by_id(teacher_id):
    """Get teacher by ID"""
    if teachers_collection is None:
        return None
    
    try:
        return teachers_collection.find_one({'_id': teacher_id})
    except Exception as e:
        print(f"❌ Error getting teacher by ID: {e}")
        return None

def update_teacher(teacher_id, update_data):
    """Update teacher data"""
    if teachers_collection is None:
        return False
    
    try:
        update_data['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = teachers_collection.update_one(
            {'_id': teacher_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        print(f"❌ Error updating teacher: {e}")
        return False

# ==================== CONVERSATION FUNCTIONS ====================

def save_conversation(user_id, mode, conversation_text):
    """Save conversation with message limit"""
    if conversations_collection is None:
        return False
    
    try:
        # Limit to last 100 messages (50 exchanges)
        messages = conversation_text.strip().split('\n') if conversation_text else []
        max_messages = 100
        
        if len(messages) > max_messages:
            # Keep only recent messages
            conversation_text = '\n'.join(messages[-max_messages:])
        
        conversations_collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    f'conversations.{mode}': conversation_text,
                    'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    f'message_count.{mode}': len(messages)
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ Error saving conversation: {e}")
        return False

def get_conversation(user_id, mode):
    """Get conversation for user and mode"""
    if conversations_collection is None:
        return ''
    
    try:
        doc = conversations_collection.find_one({'user_id': user_id})
        if doc and 'conversations' in doc:
            return doc['conversations'].get(mode, '')
        return ''
    except Exception as e:
        print(f"❌ Error getting conversation: {e}")
        return ''

def delete_conversation(user_id, mode):
    """Delete conversation history"""
    if conversations_collection is None:
        return False
    
    try:
        conversations_collection.update_one(
            {'user_id': user_id},
            {'$unset': {f'conversations.{mode}': ''}}
        )
        return True
    except Exception as e:
        print(f"❌ Error deleting conversation: {e}")
        return False

def get_all_conversations(user_id):
    """Get all conversations for a user"""
    if conversations_collection is None:
        return {}
    
    try:
        doc = conversations_collection.find_one({'user_id': user_id})
        if doc and 'conversations' in doc:
            return doc['conversations']
        return {}
    except Exception as e:
        print(f"❌ Error getting all conversations: {e}")
        return {}

# ==================== UTILITY FUNCTIONS ====================

def check_connection():
    """Check if MongoDB is connected"""
    return client is not None and db is not None

def get_database_stats():
    """Get database statistics"""
    if db is None:
        return None
    
    try:
        stats = {
            'users': users_collection.count_documents({}) if users_collection is not None else 0,
            'teachers': teachers_collection.count_documents({}) if teachers_collection is not None else 0,
            'conversations': conversations_collection.count_documents({}) if conversations_collection is not None else 0
        }
        return stats
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")
        return None

# Print connection status on import
if __name__ != "__main__":
    if check_connection():
        stats = get_database_stats()
        if stats:
            print(f"📊 Database stats: {stats['users']} users, {stats['teachers']} teachers, {stats['conversations']} conversations")
    else:
        print("⚠️ Database not connected - data will not persist!")
