from flask import Blueprint, render_template

auth = Blueprint("auth", __name__)

@auth.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@auth.route("/login")
def login():
    return render_template("login.html")