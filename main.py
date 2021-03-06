import datetime as dt
import os
from functools import wraps
from os import abort
from flask import Flask, render_template, redirect, url_for, flash, request, g
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date
from sqlalchemy import ForeignKey, Column
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, ContactForm
from flask_gravatar import Gravatar
import time

import smtplib
my_email = os.environ.get("EMAIL")
password = os.environ.get("EMAIL_PASS")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
ckeditor = CKEditor(app)
Bootstrap(app)

# LOGIN MANAGER
login_manager = LoginManager()
login_manager.init_app(app)

# GRAVATAR
gravatar = Gravatar(app,
                    size=150,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# CONNECT TO DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite://blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# CONFIGURE DATABASE TABLES

class User(UserMixin, db.Model):
    __tablename__ = "users"
    # RELATIONSHIPS
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")
    # TABLE DATA
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250), unique=True,)
    password = db.Column(db.String(250))
    name = db.Column(db.String(150))


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    # RELATIONSHIPS
    author_id = db.Column(db.Integer, db.ForeignKey("users.id")) # users refers to the DATABASE TABLE and not the CLASS!!! Make it different from class name, as it clashes and comes back with an error!!!
    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="parent_post") #  PARENT RELATIONSHIP
    # TABLE DATA
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)

class Comment(db.Model):
    __tablename__="comments"

    # Comments from author (CHILD)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")

    # Comments for blog post (CHILD)
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")
    # TABLE DATA
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)

db.create_all()


# Decorator to check admin status

def is_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return "Sorry, you are not authorized to see this content."
        return f(*args, **kwargs)
    return decorated_function


# APP URLs


@app.route('/')
def get_all_posts():
    posts = BlogPost.query.all()
    return render_template("index.html", all_posts=posts)


@app.route('/register', methods=["GET", "POST"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        if User.query.filter_by(email=register_form.email.data).first():
            flash("You have already got an account. Login instead")
            time.sleep(2)
            return redirect(url_for('login'))
        hashed_and_salted_pwd = generate_password_hash(
            password=request.form.get("password"),
            method="pbkdf2:sha256",
            salt_length=8
        )
        new_user = User(
            name=register_form.name.data,
            email=register_form.email.data,
            password=hashed_and_salted_pwd
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect('/')
    return render_template("register.html", form=register_form)


@app.route('/login', methods=["POST", "GET"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        email = login_form.email.data
        password = login_form.password.data
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Sorry, no such account registered.")
            return redirect(url_for('login'))
        elif not check_password_hash(pwhash=user.password, password=password):
            flash("Sorry, your password seems to be wrong.")
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect('/')
    return render_template("login.html", form=login_form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = BlogPost.query.get(post_id)
    all_post_comments = Comment.query.filter_by(post_id=requested_post.id)

    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = Comment(
                author_id=current_user.id,
                post_id=requested_post.id,
                text=comment_form.comment_text.data
            )
            db.session.add(new_comment)
            db.session.commit()
        return redirect(url_for("show_post", post_id=requested_post.id))
    return render_template("post.html", post=requested_post, form=comment_form, comments=all_post_comments)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=['GET', 'POST'])
def contact():
    contact_form = ContactForm()
    if contact_form.validate_on_submit():
        name = contact_form.name.data
        email = contact_form.email.data
        tel = contact_form.phone.data
        message = contact_form.message.data
        send_mail(email, name, tel, message)
        flash("Message is sent")
        return redirect(url_for('contact'))
    return render_template("contact.html", form=contact_form)



@app.route("/new-post", methods=["GET", "POST"])
@is_admin
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


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@is_admin
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))

    return render_template("make-post.html", form=edit_form)


@app.route("/delete/<int:post_id>", methods=["GET", "POST"])
@is_admin
def delete_post(post_id):
    post_to_delete = BlogPost.query.get(post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.context_processor  # to make function useful with jinja templates on the whole site
def footer_datetime():
    year = dt.datetime.now().strftime("%Y")
    return dict(year=year)  # This is the way to return the function, so it could be used throughout the website.


# EMAIL SENDER
def send_mail(email, name, tel, message):
    with smtplib.SMTP("smtp.gmail.com") as connection:
        connection.starttls()
        connection.login(user=my_email, password=password)
        connection.sendmail(from_addr=my_email,
                            to_addrs="naskoia7@gmail.com",
                            msg=f"Message from Nasko's web blog ({email})"
                                "\n\n "
                                f"Name: {name}, phone {tel}, message: \n {message}"
                            )



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
