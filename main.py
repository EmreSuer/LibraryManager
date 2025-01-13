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
    #Relationship to the Transaction table
    transactions = db.relationship('Transaction', backref='user', lazy=True)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    genre = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    is_borrowed = db.Column(db.Boolean, nullable=True, default=False)
    is_returned = db.Column(db.Boolean, nullable=True, default=False)  

    #Foreign key to the user table
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    #Relationship to the Transaction table
    transactions = db.relationship('Transaction', backref='book', lazy=True)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_returned = db.Column(db.Boolean, nullable=True, default=False)
    borrow_date = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(150), nullable=True, default="Borrowed")





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



@app.route("/add_book", methods=["GET", "POST"])
@login_required
def add_book():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        publisher = request.form.get("publisher")
        year = request.form.get("year")
        
        # Call Open Library API to search for book details
        try:
            response = requests.get(f"https://openlibrary.org/search.json?title={title}&author={author}&publisher={publisher}&year={year}")
            response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
            data = response.json()
        except requests.exceptions.RequestException as e:
            flash(f"An error occurred while contacting the Open Library API: {e}")  # Log the error message
            return redirect(url_for("add_book"))
        except ValueError:
            flash("Received invalid response from the Open Library API.")
            return redirect(url_for("add_book"))
        
        if data['docs']:
            book_data = data['docs'][0]  # Get the first result
            new_book = Book(
                title=book_data.get('title', title),
                author=book_data.get('author_name', [author])[0],
                genre=book_data.get('subject', ['Unknown'])[0],  # Default to 'Unknown' if no genre
                description=book_data.get('first_sentence', ['No description available.'])[0],  # Default description
                due_date=datetime.now(timezone.utc),  # Set a default due date
                user_id=current_user.id,  # Associate with the logged-in user
                cover_image=book_data.get('cover_i', None)
            )
            db.session.add(new_book)
            db.session.commit()
            flash("Book added successfully!")
            return redirect(url_for("list_books"))
        else:
            flash("No book found with the provided details.")
            return redirect(url_for("add_book"))
    return render_template("add_book.html")


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
    book_to_delete = Book.query.get_or_404(book_id)  # Get the book or return a 404 error
    if book_to_delete.user_id == current_user.id:  # Ensure the book belongs to the current user
        db.session.delete(book_to_delete)
        db.session.commit()
        flash("Book deleted successfully!")
    else:
        flash("You do not have permission to delete this book.")
    return redirect(url_for("list_books"))












if __name__ == "__main__":

    with app.app_context():
        db.create_all()
    
    app.run(debug=True)
