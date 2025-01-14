from flask import Flask, render_template, redirect, url_for, request, flash 
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash 
import requests

# Load environment variables
load_dotenv()

# App configuration
app = Flask(__name__)

# Secret key configuration
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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



class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    genre = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    date_book_finished = db.Column(db.DateTime, nullable=False)
    cover_image = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Float, nullable=True)

    #Foreign key to the user table
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)



# Load user
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))  # Retrieve the user from the database


# Routes
@app.route("/")
@login_required
def home():
    return render_template("index.html")



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


        return redirect(url_for("home"))
    return render_template("register.html")



# Add a list of predefined genres
GENRES = ["Romance", "Action", "Adventure", "Science Fiction", "Fantasy", "Mystery", "Non-Fiction"]

@app.route("/add_book", methods=["GET", "POST"])
@login_required
def add_book():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        genre = request.form.get("genre")  # Get the selected genre
        image_url = request.form.get("image_url")  # Get the image URL
        rating = request.form.get("rating")  # Get the rating from the form

        # Validate the rating
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
            rating = None  # Default to None if no rating is provided

        new_book = Book(
            title=title,
            author=author,
            genre=genre,  # Use the selected genre
            notes="No notes available.",  # Default notes
            date_book_finished=datetime.now(timezone.utc),  # Set the current date
            user_id=current_user.id,  # Associate with the logged-in user
            cover_image=image_url,  # Store the image URL
            rating=rating  # Store the rating
        )
        db.session.add(new_book)
        db.session.commit()
        flash("Book added successfully!")
        return redirect(url_for("list_books"))
    return render_template("add_book.html", genres=GENRES)  # Pass genres to the template


@app.route("/search_books", methods=["GET"])
@login_required
def search_books():
    query = request.args.get("query")
    if query:
        try:
            response = requests.get(f"https://openlibrary.org/search.json?q={query}")
            response.raise_for_status()
            data = response.json()
            return render_template("search_results.html", books=data['docs'])
        except requests.exceptions.RequestException as e:
            flash(f"An error occurred while contacting the Open Library API: {e}")
            return redirect(url_for("add_book"))
    return redirect(url_for("add_book"))


@app.route("/list_books")
@login_required
def list_books():
    user_books = Book.query.filter_by(user_id=current_user.id).all()  
    return render_template("list_books.html", books=user_books)  


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
    
    new_book = Book(
        title=title,
        author=author,
        genre=genre,
        description=description,
        due_date=datetime.now(timezone.utc),  # Set a default due date
        user_id=current_user.id  # Associate with the logged-in user
    )
    db.session.add(new_book)
    db.session.commit()
    flash("Book added to your library successfully!")
    return redirect(url_for("list_books"))


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

    

        # Check if required fields are filled
        if not title or not author or not genre:
            flash("All fields are required.")
            return redirect(url_for("edit_book", book_id=book.id))

        # Handle rating input
        try:
            book.rating = float(rating) if rating else None  # Convert to float or set to None
        except ValueError:
            flash("Invalid rating. Please enter a number between 0 and 10.")
            return redirect(url_for("edit_book", book_id=book.id))

        # Update the book details
        book.title = title
        book.author = author
        book.genre = genre

        db.session.commit()
        return redirect(url_for("list_books"))
    
    return render_template("edit_book.html", book=book, genres=GENRES)  # Pass genres to the template



    
if __name__ == "__main__":

    with app.app_context():
        db.create_all()
    
    app.run(debug=True)
