from flask import Flask, render_template, redirect, url_for, request, flash 
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash 
import requests
from werkzeug.utils import secure_filename
import re

# Load environment variables
load_dotenv()

# App configuration
app = Flask(__name__)

# Secret key configuration
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add these configurations after your existing app configurations
UPLOAD_FOLDER = 'static/uploads/covers'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize extensions
db = SQLAlchemy(app)

login_manager = LoginManager(app)
# The name of the view to redirect to when the user needs to log in.
login_manager.login_view = "login"


# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    #Relationship to the Book table
    books = db.relationship('Book', backref='user', lazy=True)
    shelves = db.relationship('Shelf', backref='user', lazy=True)



class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    genre = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    date_book_finished = db.Column(db.String(150), nullable=True)
    cover_image = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='mylibrary')  

    #Foreign key to the user table
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shelf_id = db.Column(db.Integer, db.ForeignKey('shelf.id'), nullable=True)



class Shelf(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    
    # Relationship to the Book table
    books = db.relationship('Book', backref='shelf', lazy=True)


# Load user
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))  


# Routes
@app.route("/")
@login_required
def home():
    shelves = Shelf.query.filter_by(user_id=current_user.id).all()
    wishlist_books = Book.query.filter_by(
        user_id=current_user.id, 
        category='wishlist',
    ).all()
    
    # Get books for each shelf
    shelf_books = {}
    for shelf in shelves:
        shelf_books[shelf.id] = Book.query.filter_by(
            shelf_id=shelf.id,
        ).all()
    
    return render_template("index.html", 
                         shelves=shelves,
                         shelf_books=shelf_books,
                         wishlist_books=wishlist_books)



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("User not found. Please register.")
            return redirect(url_for("register"))
        if not check_password_hash(user.password, password):
            flash("Incorrect password. Please try again.")
            return redirect(url_for("login"))
        
        if user and check_password_hash(user.password, password):  
            login_user(user)
            return redirect(url_for("home"))
        else:
            return redirect(url_for("login"))
    return render_template("login.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        # Create default "MyLibrary"  shelf 
        my_library = Shelf(name="MyLibrary", user_id=new_user.id)
        db.session.add(my_library)
        db.session.commit()

        return redirect(url_for("login"))
    return render_template("register.html")



GENRES = [
    # Most Common Genres
    "Fiction",
    "Non-Fiction", 
    "Mystery/Thriller",
    "Romance",
    "Science Fiction",
    "Fantasy",
    "Literary Fiction",
    "Historical Fiction",
    "Biography/Memoir",
    "Self-Help",
    
    # Additional Fiction Genres
    "Action/Adventure",
    "Contemporary Fiction",
    "Crime Fiction",
    "Horror",
    "Young Adult",
    "Children's",
    "Graphic Novel",
    "Short Stories",
    "Poetry",
    "Drama",
    
    # Additional Non-Fiction Categories
    "History",
    "Science",
    "Philosophy",
    "Psychology",
    "Business",
    "Politics",
    "Travel",
    "Art/Photography",
    "Cooking/Food",
    "Health/Wellness",
    "Religion/Spirituality",
    "Education",
    "Technology",
    "True Crime",
    "Essays",
    "Reference"
]

@app.route("/add_book", methods=["GET", "POST"])
@login_required
def add_book():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        genre = request.form.get("genre")
        image_url = request.form.get("image_url")
        rating = request.form.get("rating")
        date_finished = request.form.get("date_book_finished")

        # Validate date format if provided
        if date_finished:
            # Check if date matches MM/YYYY format
            if not re.match(r'^(0[1-9]|1[0-2])\/[0-9]{4}$', date_finished):
                flash("Date must be in MM/YYYY format (e.g., 03/2024)")
                return redirect(url_for("add_book"))
            
            # Verify it's a valid date
            try:
                datetime.strptime(date_finished, '%m/%Y')
            except ValueError:
                flash("Invalid date")
                return redirect(url_for("add_book"))

        # Validate rating if provided
        if rating:
            try:
                rating = float(rating)
                if rating < 0 or rating > 10:
                    flash("Rating must be between 0 and 10.")
                    return redirect(url_for("add_book"))
            except ValueError:
                flash("Invalid rating. Please enter a number between 0 and 10.")
                return redirect(url_for("add_book"))
        else:
            rating = None

        shelf_id = request.form.get("shelf_id")
        category = 'wishlist' if not shelf_id else None

        new_book = Book(
            title=title,
            author=author,
            genre=genre,
            notes="No notes available.",
            date_book_finished=date_finished,
            user_id=current_user.id,
            cover_image=image_url,
            rating=rating,
            shelf_id=shelf_id,
            category=category
        )
        db.session.add(new_book)
        db.session.commit()
        flash("Book added successfully!")
        return redirect(url_for("home"))
    
    shelves = Shelf.query.filter_by(user_id=current_user.id).all()
    return render_template("add_book.html", genres=GENRES, shelves=shelves)


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    """Handle Google Books search"""
    if request.method == "POST":
        query = request.form.get("query")
        return redirect(url_for("search_results", query=query))
    return render_template("search.html")


@app.route("/search_in_library", methods=["GET", "POST"])
@login_required
def search_in_library():
    """Handle library search"""
    if request.method == "POST":
        search_query = request.form.get("query", "").strip().lower()
        
        # If no search query provided, return all books
        if not search_query:
            return redirect(url_for("list_books"))
        
        # SQL Query by using SQLAlchemy
        search_results = Book.query.filter(
            db.and_(
                Book.user_id == current_user.id, # Filter by the current user's books
                db.or_(
                    db.func.lower(Book.title).contains(search_query),
                    db.func.lower(Book.author).contains(search_query),
                    db.func.lower(Book.genre).contains(search_query),
                    db.func.lower(Book.notes).contains(search_query),
                    db.func.lower(Book.description).contains(search_query)
                )  # OR conditions for multiple fields to search across
            )
        ).all() # execute the query and return all results
        
        return render_template("list_books.html", 
                             books=search_results, 
                             search_query=search_query)
    
    # If GET request, show the search form
    return render_template("library_search.html")


@app.route("/search_results")
@login_required
def search_results():
    query = request.args.get("query")
    if query:
        try:
            response = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}")
            response.raise_for_status()
            data = response.json()
            
            # Process the API response to extract only the needed information
            processed_books = []
            for item in data.get('items', []):
                volume_info = item.get('volumeInfo', {})
                # Get image URL and replace http with https if needed
                image_url = volume_info.get('imageLinks', {}).get('thumbnail', '')
                if image_url.startswith('http://'):
                    image_url = 'https://' + image_url[7:]
                
                processed_books.append({
                    'id': item.get('id', ''),
                    'title': volume_info.get('title', 'Unknown Title'),
                    'authors': volume_info.get('authors', ['Unknown Author']),
                    'description': volume_info.get('description', 'No description available'),
                    'imageLinks': {'thumbnail': image_url} if image_url else {},
                    'categories': volume_info.get('categories', ['Uncategorized'])
                })
            
            # Get user's shelves
            shelves = Shelf.query.filter_by(user_id=current_user.id).all()
            
            return render_template("search_results.html", books=processed_books, shelves=shelves)
        except requests.exceptions.RequestException as e:
            flash(f"An error occurred while contacting the Google Books API: {e}")
            return redirect(url_for("home"))
    return redirect(url_for("home"))


@app.route("/list_books")
@login_required
def list_books():
    # Get all user's books
    user_books = Book.query.filter_by(user_id=current_user.id)
    
    # Get filter parameters
    sort_by = request.args.get('sort_by', 'title')  # Default sort by title
    order = request.args.get('order', 'asc')  # Default ascending order
    year_filter = request.args.get('year')
    
    # Get unique years from date_book_finished for the dropdown
    years_query = db.session.query(
        db.func.distinct(db.func.substr(Book.date_book_finished, -4))
    ).filter(
        Book.user_id == current_user.id,
        Book.date_book_finished.isnot(None)
    ).order_by(
        db.func.substr(Book.date_book_finished, -4).desc()
    )
    available_years = [year[0] for year in years_query.all() if year[0]]
    
    # Apply year filter if specified
    if year_filter:
        user_books = user_books.filter(db.func.substr(Book.date_book_finished, -4) == year_filter)
    
    # Apply sorting based on parameters
    if sort_by == 'rating':
        # Sort by rating, putting None values at the end
        if order == 'desc':
            user_books = user_books.order_by(
                Book.rating.is_(None),
                Book.rating.desc()
            )
        else:
            user_books = user_books.order_by(
                Book.rating.is_(None),
                Book.rating.asc()
            )
    elif sort_by == 'date':
        # Extract first year and then month for sorting
        if order == 'desc':
            user_books = user_books.order_by(
                Book.date_book_finished.is_(None), 
                db.func.substr(Book.date_book_finished, -4).desc(), # Substring SQL function, -4 means last 4 characters
                db.func.substr(Book.date_book_finished, 1, 2).desc() # 1, 2 means first 2 characters
            )
        else:
            user_books = user_books.order_by(
                db.func.substr(Book.date_book_finished, -4).asc(),  
                db.func.substr(Book.date_book_finished, 1, 2).asc(),  
                Book.date_book_finished.is_(None)
            )
    else:  # Default sort by title
        if order == 'desc':
            user_books = user_books.order_by(Book.title.desc())
        else:
            user_books = user_books.order_by(Book.title.asc())
    
    # Execute query
    books = user_books.all()
    
    return render_template(
        "list_books.html", 
        books=books,
        current_sort=sort_by,
        current_order=order,
        available_years=available_years,
        current_year=year_filter
    )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route("/add_book_to_library", methods=["POST"])
@login_required
def add_book_to_library():
    title = request.form.get("title")
    author = request.form.get("author")
    genre = request.form.get("genre")
    description = request.form.get("description")
    cover_image = request.form.get("cover_image")
    shelf_id = request.form.get("shelf_id")
    
    # If no shelf_id provided, book goes to wishlist
    if not shelf_id:
        category = 'wishlist'
        shelf_id = None
    else:
        category = 'mylibrary'
        # Verify the shelf belongs to the user
        shelf = Shelf.query.get(shelf_id)
        if not shelf or shelf.user_id != current_user.id:
            flash("Invalid shelf selected!")
            return redirect(url_for("home"))

    new_book = Book(
        title=title,
        author=author,
        genre=genre,
        description=description,
        cover_image=cover_image,
        user_id=current_user.id,
        shelf_id=shelf_id,
        category=category,
    )

    db.session.add(new_book)
    db.session.commit()
    flash("Book added to your library successfully!")
    return redirect(url_for("home"))


@app.route("/delete_book/<int:book_id>", methods=["POST"])
@login_required
def delete_book(book_id):
    book_to_delete = Book.query.get_or_404(book_id)  
    if book_to_delete.user_id == current_user.id: 
        db.session.delete(book_to_delete)
        db.session.commit()
        flash("Book deleted successfully!")
    else:
        flash("You do not have permission to delete this book.")
    return redirect(url_for("list_books"))


@app.route("/save_notes/<int:book_id>", methods=["POST"])
@login_required
def save_notes(book_id):
    notes = request.form.get("notes")
    book = Book.query.get(book_id)
    if book:
        book.notes = notes  
        db.session.commit()
        flash("Notes saved successfully!")
    return redirect(url_for("list_books"))


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
@login_required
def edit_book(book_id):
    book = Book.query.get(book_id)
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        genre = request.form.get("genre")
        rating = request.form.get("rating")
        date_finished = request.form.get("date_book_finished")

        # Check if required fields are filled
        if not title or not author or not genre:
            flash("All fields are required.")
            return redirect(url_for("edit_book", book_id=book.id))

        # Validate date format if provided
        if date_finished:
            # Check if date matches MM/YYYY format
            if not re.match(r'^(0[1-9]|1[0-2])\/[0-9]{4}$', date_finished):
                flash("Date must be in MM/YYYY format (e.g., 03/2024)")
                return redirect(url_for("edit_book", book_id=book.id))
            
            # Verify it's a valid date
            try:
                datetime.strptime(date_finished, '%m/%Y')
            except ValueError:
                flash("Invalid date")
                return redirect(url_for("edit_book", book_id=book.id))

        # Handle rating input
        try:
            book.rating = float(rating) if rating else None
        except ValueError:
            flash("Invalid rating. Please enter a number between 0 and 10.")
            return redirect(url_for("edit_book", book_id=book.id))

        # Update the book details
        book.title = title
        book.author = author
        book.genre = genre
        book.date_book_finished = date_finished

        db.session.commit()
        flash("Book updated successfully!")
        return redirect(url_for("book_details", book_id=book.id))
    
    return render_template("edit_book.html", book=book, genres=GENRES)


@app.route("/update_cover_image/<int:book_id>", methods=["POST"])
@login_required
def update_cover_image(book_id):
    book = Book.query.get_or_404(book_id)
    

    if book.user_id != current_user.id:
        flash("You don't have permission to modify this book.")
        return redirect(url_for('list_books'))
    
    cover_image_url = request.form.get('cover_image_url')
    if cover_image_url:
        book.cover_image = cover_image_url
        db.session.commit()
        flash('Cover image updated successfully!')
    else:
        flash('Please provide an image URL')
    
    return redirect(url_for('list_books'))


@app.route("/upload_cover_image/<int:book_id>", methods=["POST"])
@login_required
def upload_cover_image(book_id):
    book = Book.query.get_or_404(book_id)
    

    if book.user_id != current_user.id:
        flash("You don't have permission to modify this book.")
        return redirect(url_for('list_books'))
    
    if 'cover_image_file' not in request.files:
        flash('No file selected')
        return redirect(url_for('list_books'))
        
    file = request.files['cover_image_file']
    
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('list_books'))
        
    if file and allowed_file(file.filename):
        # Create a unique filename
        filename = secure_filename(f"{book_id}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Delete old file if it exists
        if book.cover_image and os.path.exists(book.cover_image.replace('/static/', '', 1)):
            try:
                os.remove(book.cover_image.replace('/static/', '', 1))
            except:
                pass
        
        # Save the new file
        file.save(filepath)
        
        # Update database with new image path
        book.cover_image = f"/static/uploads/covers/{filename}"
        db.session.commit()
        
        flash('Cover image updated successfully!')
    else:
        flash('Invalid file type. Please use PNG, JPG, JPEG, or GIF files.')
        
    return redirect(url_for('list_books'))


@app.route("/book/<int:book_id>")
@login_required
def book_details(book_id):
    book = Book.query.get_or_404(book_id)
    if book.user_id != current_user.id:
        flash("You don't have permission to view this book.")
        return redirect(url_for('list_books'))
    
    # Get all shelves for the move functionality
    shelves = Shelf.query.filter_by(user_id=current_user.id).all()
    
    return render_template("book_details.html", book=book, shelves=shelves)



@app.route("/add_shelf", methods=["POST"])
@login_required
def add_shelf():
    shelf_name = request.form.get("shelf_name")
    if not shelf_name:
        flash("Shelf name is required!")
        return redirect(url_for("home"))
        
    # Check if shelf already exists for this user
    existing_shelf = Shelf.query.filter_by(user_id=current_user.id, name=shelf_name).first()
    if existing_shelf:
        flash("A shelf with this name already exists!")
        return redirect(url_for("home"))
        
    new_shelf = Shelf(name=shelf_name, user_id=current_user.id)
    db.session.add(new_shelf)
    db.session.commit()
    flash(f"Shelf '{shelf_name}' created successfully!")
    return redirect(url_for("home"))

@app.route("/delete_shelf/<int:shelf_id>", methods=["POST"])
@login_required
def delete_shelf(shelf_id):
    shelf = Shelf.query.get_or_404(shelf_id)
    if shelf.user_id != current_user.id:
        flash("You don't have permission to delete this shelf!")
        return redirect(url_for("home"))
    
       
    # Move all books from this shelf to MyLibrary
    my_library = Shelf.query.filter_by(user_id=current_user.id, name="MyLibrary").first()
    Book.query.filter_by(shelf_id=shelf_id).update({Book.shelf_id: my_library.id})
    
    db.session.delete(shelf)
    db.session.commit()
    flash("Shelf deleted successfully!")
    return redirect(url_for("home"))

@app.route("/move_book/<int:book_id>", methods=["POST"])
@login_required
def move_book(book_id):
    book = Book.query.get_or_404(book_id)
    if book.user_id != current_user.id:
        flash("You don't have permission to move this book!")
        return redirect(url_for("home"))
    
    destination = request.form.get("destination")
    if not destination:
        flash("Invalid move request: No destination specified!")
        return redirect(url_for("book_details", book_id=book.id))
    
    if destination == "wishlist":
        # Move to wishlist
        book.shelf_id = None
        book.category = 'wishlist'
    elif destination.startswith("shelf_"):
        # Move to a shelf
        try:
            shelf_id = int(destination.split("_")[1])
            shelf = Shelf.query.get(shelf_id)
            if shelf and shelf.user_id == current_user.id:
                book.shelf_id = shelf_id
                book.category = 'mylibrary'  # Set category to mylibrary when moving to a shelf
            else:
                flash("Invalid shelf selected!")
                return redirect(url_for("book_details", book_id=book.id))
        except (IndexError, ValueError):
            flash("Invalid destination format!")
            return redirect(url_for("book_details", book_id=book.id))
    else:
        flash("Invalid destination selected!")
        return redirect(url_for("book_details", book_id=book.id))
    
    db.session.commit()
    flash("Book moved successfully!")
    return redirect(url_for("home"))


if __name__ == "__main__":

    with app.app_context():
        db.create_all()
    
    app.run(debug=True)
