import dotenv
import os
from datetime import date
from collections.abc import Callable
from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

dotenv.load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQL_PATH")
ckeditor = CKEditor(app)
Bootstrap5(app)


class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    author: Mapped["User"] = relationship("User", back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="post")

class User(db.Model, UserMixin):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    posts: Mapped[list[BlogPost]] = relationship("BlogPost", back_populates="author")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="author")

class Comment(db.Model):
    __tablename__ = "comments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(1028), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_posts.id"))
    author: Mapped[User] = relationship("User", back_populates="comments")
    post: Mapped[BlogPost] = relationship("BlogPost", back_populates="comments")

with app.app_context():
    db.create_all()


login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(
    app,
    size=100,
    rating='g',
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)


def admin_only(function: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        if current_user.id == 1:
            return function(*args, **kwargs)
        else:
            abort(403)
    
    return wrapper


@login_manager.user_loader
def user_loader(user_id: str) -> User | None:
    return get_user(int(user_id))

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        user = User(
            name = form.name.data,
            email = form.email.data,
            password = hash(form.password.data)
        )
        
        if user.email in [user.email for user in get_users()]:
            flash("The email is already registered.", "email")
            return redirect(url_for("login"))
        
        db_add(user)
        
        if login_user(user):
            return redirect(url_for("get_all_posts"))
    
    return render_template("register.jinja", form=form)

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        user: User = get_user_email(form.email.data)
        
        if user:
            if check_password_hash(user.password, form.password.data):
                if login_user(user):
                    return redirect(url_for("get_all_posts"))
            else:
                flash("Password invalid. Try again.", "warning")
        else:
            flash("Email does not exist. Try again.", "warning")
    
    return render_template("login.jinja", form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))

@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.jinja", all_posts=posts)

@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    
    requested_post = db.get_or_404(BlogPost, post_id)
    
    if form.validate_on_submit():
        if current_user.is_anonymous():
            flash("You must be logged in to comment.", "email")
            return redirect(url_for("login"))
        
        db_add(Comment(
            text=form.body.data,
            user_id=current_user.id,
            post_id=post_id
        ))
    
    return render_template("post.jinja", post=requested_post, form=form)

@app.route("/new-post", methods=["GET", "POST"], endpoint="add_new_post")
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        
        db.session.add(new_post)
        db.session.commit()
        
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"], endpoint="edit_post")
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)

@app.route("/delete/<int:post_id>", endpoint="delete_post")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

def hash(string: str) -> str:
    return generate_password_hash(
        string,
        "pbkdf2:sha256",
        salt_length=16
    )

def db_add(object) -> None:
    db.session.add(object)
    db.session.commit()

def get_users() -> list[User]:
    result = db.session.execute(
        db.select(User).order_by(User.id)
    )
    
    return result.scalars().fetchall()

def get_user_email(email: str) -> User:
    result = db.session.execute(
        db.select(User).where(User.email == email)
    )
    
    return result.scalar()

def get_user(id: int) -> User:
    return db.get_or_404(User, id)


if __name__ == "__main__":
    app.run(debug=False)
