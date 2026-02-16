# 🗄️ MongoDB Atlas Setup Guide for Gayathri Smart Speak V6

## 🎯 Why MongoDB Atlas?

**Your research was excellent!** MongoDB Atlas solves the critical data persistence problem:

- ✅ **FREE Forever** (not just a trial)
- ✅ **512MB Storage** - Enough for 50,000+ students
- ✅ **Permanent Data** - Survives Render restarts
- ✅ **Automatic Backups** - Your data is safe
- ✅ **Easy Integration** - Works perfectly with Render

---

## 📋 Step-by-Step Setup

### Part 1: Create MongoDB Atlas Account

1. **Go to:** https://www.mongodb.com/cloud/atlas/register
2. **Sign up** with email or Google account
3. **Choose FREE tier** (M0 Sandbox)
4. **Select:**
   - Cloud Provider: AWS (recommended)
   - Region: Choose closest to your Render region
   - Cluster Name: Keep default or use "GayathriSmartSpeak"
5. **Click:** "Create Cluster" (takes 1-3 minutes)

---

### Part 2: Configure Database Access

#### Step 1: Create Database User

1. Click **"Database Access"** (left sidebar)
2. Click **"Add New Database User"**
3. Fill in:
   - **Authentication Method:** Password
   - **Username:** `smartspeak_admin`
   - **Password:** Click "Autogenerate Secure Password" → **COPY THIS!**
   - **Database User Privileges:** "Read and write to any database"
4. Click **"Add User"**

**⚠️ IMPORTANT:** Save this password - you'll need it for the connection string!

#### Step 2: Whitelist IP Addresses

1. Click **"Network Access"** (left sidebar)
2. Click **"Add IP Address"**
3. Select **"Allow Access from Anywhere"** (0.0.0.0/0)
   - ⚠️ Note: For production, you'd whitelist specific IPs, but Render uses dynamic IPs
4. Click **"Confirm"**

---

### Part 3: Get Connection String

1. Click **"Database"** (left sidebar)
2. Click **"Connect"** on your cluster
3. Choose **"Connect your application"**
4. Select:
   - **Driver:** Python
   - **Version:** 3.12 or later
5. **Copy the connection string**

It will look like:
```
mongodb+srv://smartspeak_admin:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

6. **Replace** `<password>` with the actual password you saved earlier

**Final connection string example:**
```
mongodb+srv://smartspeak_admin:MySecurePass123@cluster0.abc12.mongodb.net/?retryWrites=true&w=majority
```

---

### Part 4: Configure Your Application

#### For Local Development:

Edit your `.env` file:
```env
GROQ_API_KEY=your_groq_api_key_here
MONGODB_URI=mongodb+srv://smartspeak_admin:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

#### For Render Deployment:

1. Go to your Render dashboard
2. Select your web service
3. Click **"Environment"** tab
4. Add two environment variables:

**Variable 1:**
- Key: `GROQ_API_KEY`
- Value: Your GROQ API key

**Variable 2:**
- Key: `MONGODB_URI`
- Value: Your complete MongoDB connection string

5. Click **"Save Changes"**
6. Render will automatically redeploy

---

## 🧪 Test Your Connection

### Quick Test (Optional):

Create a test file `test_mongodb.py`:

```python
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

try:
    client = MongoClient(os.getenv('MONGODB_URI'))
    db = client['gayathri_smart_speak']
    
    # Test write
    test_collection = db['test']
    test_collection.insert_one({'test': 'connection successful'})
    
    # Test read
    result = test_collection.find_one({'test': 'connection successful'})
    
    if result:
        print("✅ MongoDB connection successful!")
        test_collection.delete_one({'test': 'connection successful'})
    else:
        print("❌ Connection failed")
    
    client.close()
except Exception as e:
    print(f"❌ Error: {e}")
```

Run:
```bash
python test_mongodb.py
```

---

## 📊 Understanding Your Database Structure

### Database: `gayathri_smart_speak`

**Collections (like tables):**

1. **`students`** - Student accounts and progress
   ```json
   {
     "_id": "1234",
     "name": "John Doe",
     "password": "hashed_password",
     "class": "10",
     "division": "A",
     "level": 5,
     "total_xp": 150,
     "total_stars": 45,
     "mode_stats": {...},
     "created_at": "2026-01-15 10:30:00",
     "last_active": "2026-02-15 14:20:00"
   }
   ```

2. **`teachers`** - Teacher accounts
   ```json
   {
     "_id": "teach1",
     "name": "Ms. Smith",
     "password": "hashed_password",
     "created_at": "2026-01-10 09:00:00"
   }
   ```

### Capacity Calculations:

```
Average Student Record: ~10 KB
512 MB = 512,000 KB
512,000 ÷ 10 = 51,200 students

Conservative Estimate: 40,000-50,000 students
With room for growth!
```

---

## 🗑️ 6-Month Inactivity Cleanup

**V6 Feature:** Automatically removes inactive users

### How It Works:

1. **Checks** last_active date for each user
2. **If inactive > 6 months:** Account is deleted
3. **Runs** automatically every 24 hours
4. **Logs** deletions for admin review

### Manual Cleanup (if needed):

In MongoDB Atlas dashboard:
1. Go to **"Collections"**
2. Click **"students"** collection
3. Find inactive users:
   ```javascript
   {
     "last_active": {
       "$lt": new Date(new Date() - 180*24*60*60*1000)
     }
   }
   ```
4. Delete if needed

---

## 🔐 Security Best Practices

### ✅ DO:
- Use strong passwords for database users
- Keep your connection string private
- Use environment variables
- Enable 2FA on MongoDB Atlas account

### ❌ DON'T:
- Share your connection string
- Commit .env to GitHub
- Use weak passwords
- Disable authentication

---

## 🚀 Migration from V5 to V6

### If You Have Existing Users:

**Option 1: Fresh Start (Recommended for testing)**
- Users re-register
- Start from clean database
- No data migration needed

**Option 2: Migrate Data (For production with existing users)**

Create `migrate_to_mongodb.py`:

```python
import json
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client['gayathri_smart_speak']

# Migrate students
try:
    with open('users_data.json', 'r') as f:
        users_data = json.load(f)
        
    for user_id, user_info in users_data.items():
        user_info['_id'] = user_id
        db.students.update_one(
            {'_id': user_id},
            {'$set': user_info},
            upsert=True
        )
    print(f"✅ Migrated {len(users_data)} students")
except FileNotFoundError:
    print("No users_data.json found - starting fresh")

# Migrate teachers
try:
    with open('teachers_data.json', 'r') as f:
        teachers_data = json.load(f)
        
    for teacher_id, teacher_info in teachers_data.items():
        teacher_info['_id'] = teacher_id
        db.teachers.update_one(
            {'_id': teacher_id},
            {'$set': teacher_info},
            upsert=True
        )
    print(f"✅ Migrated {len(teachers_data)} teachers")
except FileNotFoundError:
    print("No teachers_data.json found - starting fresh")

client.close()
print("✅ Migration complete!")
```

Run:
```bash
python migrate_to_mongodb.py
```

---

## 📈 Monitoring Your Database

### MongoDB Atlas Dashboard:

1. **Metrics Tab:**
   - See connections, operations, storage usage
   - Monitor performance

2. **Collections Tab:**
   - View all data
   - Run queries
   - Export data

3. **Alerts:**
   - Set up email alerts for:
     - Storage > 400MB (80% capacity)
     - Connection errors
     - Unusual activity

---

## 💾 Backup Strategy

### Automatic (MongoDB Atlas handles this):
- ✅ Continuous snapshots
- ✅ Point-in-time recovery
- ✅ Free tier includes basic backups

### Manual Export (optional):

```bash
# In MongoDB Atlas dashboard:
# Collections → Export Collection → JSON
```

---

## ⚠️ Free Tier Limits

**MongoDB Atlas M0 (Free):**
- ✅ Storage: 512 MB
- ✅ RAM: 512 MB (shared)
- ✅ Connections: 500 concurrent
- ✅ Bandwidth: Unlimited (reasonable use)
- ✅ Forever free!

**What happens if you exceed limits:**
- Storage > 512MB: Need to upgrade or clean old data
- For 40,000 students: You're well within limits!

---

## 🔄 Updating Your Deployment

### After MongoDB Setup:

1. **Add environment variable** to Render:
   ```
   MONGODB_URI=your_connection_string
   ```

2. **Deploy V6:**
   ```bash
   git add .
   git commit -m "Upgrade to V6 with MongoDB Atlas"
   git push origin main
   ```

3. **Render auto-deploys** (2-3 minutes)

4. **Test** the deployment:
   - Sign up a test user
   - Check MongoDB Atlas → Collections
   - Verify data is saved

---

## 🆘 Troubleshooting

### Issue: "Connection Timeout"
**Solution:**
- Check Network Access whitelist (0.0.0.0/0)
- Verify connection string has correct password
- Check if cluster is running (shouldn't sleep in free tier)

### Issue: "Authentication Failed"
**Solution:**
- Verify database user exists
- Check password in connection string (no < >)
- Ensure user has read/write permissions

### Issue: "Server Selection Timeout"
**Solution:**
- Check internet connection
- Verify MongoDB URI format
- Ensure dnspython is installed: `pip install dnspython`

### Issue: "Storage Full"
**Solution:**
- Run 6-month cleanup manually
- Check for duplicate data
- Consider upgrading (if you have 50K+ users)

---

## 📚 Useful MongoDB Commands

### View All Students:
```python
from pymongo import MongoClient
client = MongoClient(MONGODB_URI)
db = client['gayathri_smart_speak']

students = list(db.students.find({}))
print(f"Total students: {len(students)}")
```

### Count by Class:
```python
class_10_count = db.students.count_documents({'class': '10'})
print(f"Class 10 students: {class_10_count}")
```

### Find Top Students:
```python
top_students = db.students.find().sort('total_xp', -1).limit(10)
for student in top_students:
    print(f"{student['name']}: {student['total_xp']} XP")
```

---

## 🎉 Summary

**Your V6 Upgrade Includes:**
- ✅ MongoDB Atlas integration
- ✅ Permanent data storage
- ✅ 6-month inactivity cleanup
- ✅ Support for 40,000+ students
- ✅ Free forever!

**Setup Time:** ~15 minutes

**Result:** Your app now has enterprise-grade data persistence for FREE! 🚀

---

**Questions?** Check MongoDB Atlas documentation: https://docs.atlas.mongodb.com/
