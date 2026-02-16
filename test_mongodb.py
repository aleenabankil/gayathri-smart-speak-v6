#!/usr/bin/env python3
"""
MongoDB Connection Test Script
Test your MongoDB Atlas connection before deploying
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_connection():
    print("🔍 Testing MongoDB Connection...")
    print("=" * 50)
    
    # Get MongoDB URI
    mongodb_uri = os.getenv('MONGODB_URI')
    
    if not mongodb_uri or mongodb_uri == 'your_mongodb_connection_string_here':
        print("❌ ERROR: MONGODB_URI not configured!")
        print("")
        print("Please edit your .env file and add your MongoDB connection string:")
        print("MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/")
        print("")
        print("Get your connection string from MongoDB Atlas:")
        print("1. Go to https://cloud.mongodb.com/")
        print("2. Click 'Connect' on your cluster")
        print("3. Choose 'Connect your application'")
        print("4. Copy the connection string")
        return False
    
    try:
        # Attempt connection
        print(f"📡 Connecting to MongoDB...")
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        print("✅ Connection successful!")
        print("")
        
        # Get database
        db = client['gayathri_smart_speak']
        print(f"📊 Database: {db.name}")
        
        # List collections
        collections = db.list_collection_names()
        print(f"📁 Collections: {collections if collections else '(none yet - will be created on first use)'}")
        print("")
        
        # Test write
        print("📝 Testing write operation...")
        test_collection = db['test']
        result = test_collection.insert_one({'test': 'connection', 'status': 'success'})
        print(f"✅ Write successful! ID: {result.inserted_id}")
        
        # Test read
        print("📖 Testing read operation...")
        doc = test_collection.find_one({'test': 'connection'})
        if doc:
            print(f"✅ Read successful! Document: {doc}")
        else:
            print("❌ Read failed!")
            return False
        
        # Cleanup
        print("🗑️ Cleaning up test data...")
        test_collection.delete_one({'test': 'connection'})
        print("✅ Cleanup successful!")
        print("")
        
        # Summary
        print("=" * 50)
        print("🎉 All tests passed!")
        print("")
        print("Your MongoDB Atlas connection is working perfectly!")
        print("You're ready to deploy Gayathri Smart Speak V6!")
        print("=" * 50)
        
        client.close()
        return True
        
    except Exception as e:
        print("")
        print("=" * 50)
        print("❌ CONNECTION FAILED!")
        print("=" * 50)
        print(f"Error: {str(e)}")
        print("")
        print("Common issues:")
        print("")
        print("1. Network Access not configured:")
        print("   → Go to MongoDB Atlas → Network Access")
        print("   → Add IP Address → Allow Access from Anywhere (0.0.0.0/0)")
        print("")
        print("2. Database user not created:")
        print("   → Go to MongoDB Atlas → Database Access")
        print("   → Add New Database User")
        print("   → Set username/password")
        print("")
        print("3. Wrong connection string:")
        print("   → Check for typos")
        print("   → Ensure password is correct (no < >)")
        print("   → Make sure to replace <password> with actual password")
        print("")
        print("4. DNSPython not installed:")
        print("   → Run: pip install dnspython")
        print("")
        print("See MONGODB_SETUP_GUIDE.md for detailed instructions!")
        print("=" * 50)
        return False

if __name__ == "__main__":
    test_connection()
