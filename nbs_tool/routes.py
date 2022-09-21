from flask import render_template, url_for, flash, redirect, request, abort, make_response
from nbs_tool import app, db, bcrypt, mail
from nbs_tool.forms import RegistrationForm, LoginForm, UpdateAccountForm, RequestResetForm, ResetPasswordForm
from nbs_tool.models import User, Site, Ci, Nbs, Nbs_ci
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
import copy
import pdfkit
from pathlib import Path
import os
import json

cwd = Path.cwd()

config = pdfkit.configuration(wkhtmltopdf=os.path.join(cwd, r'nbs_tool/wkhtmltopdf/bin/wkhtmltopdf.exe'))

ci_importances = ["None Chosen", "High Priority", "Moderate Priority", "Low Priority", "No Problem", "Not A Concern"]
ci_tops = ["Yes", "No"]
nbs_cis = ["None Chosen", "Direct Impact", "Indirect Impact", "No Impact"]

load_page_down = False # just a variable to check whether i want to load the nbs_page on top or down (pixel wise)


@app.route("/")
@app.route("/home")
def home_page():
    return render_template('home.html', title="Home")


@app.route("/about")
def about_page():
    return render_template('about.html', title="About")


@app.route("/contact")
def contact_page():
    return render_template('contact.html', title="Contact")


@app.route("/login", methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('nbs_page'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash(f"You are logged in, welcome {user.username}!", 'info')
            if next_page:
                return redirect(next_page)
            else:
                return redirect(url_for('nbs_page'))
        else:
            flash("Login unsuccessful, please check email and password.", 'info')
    return render_template('login.html', title="Login", form=form)


@app.route("/register", methods=['GET', 'POST'])
def register_page():
    # the total concerns will be represented as a 2D python list where each row has as first element each concerns' category
    # and the rest elements of each row refer to the actual concerns of that specific category
    problems = [
        ["Urban", "Accessibility", "Green space per inhabitant", "Multifunctionality"],
        ["Environmental", "Extreme heat", "Water scarcity", "Water quality", "Flooding", "Wastewater treatment",
            "Air quality", "Biodiversity", "Share of green areas"],
        ["Social", "Community engagement", "Access to sport facilities", "Access to cultural facilities",
            "Crime", "Aesthetics", "Quality of experience"],
        ["Economic/Business", "Property value", "Unemployment", "Business activity"],
        ["PH & WB (Public Health & Well Being)", "Chronic respiratory diseases", "Cardiovascular diseases",
            "Diabetes", "Obesity", "Depression", "Physical activity", "Communicable diseases - alimentary infections",
            "Communicable diseases - vector borne diseases"]
                ]

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    if current_user.is_authenticated:
        return redirect(url_for('nbs_page'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        user = User.query.filter_by(username=form.username.data).first()

        site = Site(user_id=user.id)
        db.session.add(site)
        db.session.commit()

        site = Site.query.filter_by(user_id=user.id).first() # the user gets only one site automatically when registering to the webpage

        # the user gets all default 28 concerns created automatically for his site when registering to the webpage
        for cat in problems:
            for j in range(1, len(cat)): # in each list the item 0 refers to the category and the rest elements refer to the actual concerns
                new_ci = Ci(category=cat[0], title=cat[j], site_id=site.id)
                db.session.add(new_ci)
                db.session.commit()

        new_nbs = Nbs(site_id=site.id) # the user gets only one NBS automatically for his site when registering to the webpage
        db.session.add(new_nbs)
        db.session.commit()

        new_nbs = Nbs.query.filter_by(site_id=site.id).first()

        # the user gets automatically gets the default impacts that his one and only NBS has accross all the CIs
        for i in range(len(site.ci)):
            new_nbs_ci = Nbs_ci(nbs_id=new_nbs.id, ci_id=site.ci[i].id)
            db.session.add(new_nbs_ci)
            db.session.commit()

        flash(f'Your account has been created. Please login to access the NBS Tool!', 'info')
        return redirect(url_for('login_page'))
    return render_template('register.html', title="Register", form=form)


@app.route("/logout")
def logout_page():
    logout_user()
    flash(f'You have been logged out!', 'info')
    return redirect(url_for("home_page"))


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account_page():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit() # that's the only thing I need to do to update a column of a db in SQLAlchemy
        flash(f'Your account has been updated!', 'info')
        return redirect(url_for('account_page'))
    elif request.method == 'GET':
        form.username.data = current_user.username # When I load the account page the fields are already filled in with the current user's info
        form.email.data = current_user.email
    return render_template('account.html', title="Account", form=form)


@app.route("/delete-account", methods=['POST'])
@login_required
def delete_account():
    for site in current_user.site:
        for nbs in site.nbs:
            for nbs_ci in nbs.nbs_ci:
                db.session.delete(nbs_ci)
                db.session.commit()

            db.session.delete(nbs)
            db.session.commit()

        for ci in site.ci:
            db.session.delete(ci)
            db.session.commit()

        db.session.delete(site)
        db.session.commit()

    db.session.delete(current_user)
    db.session.commit()

    flash('Your account has been deleted!', 'info')
    return redirect(url_for('home_page'))


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message(subject='Password Reset Request',
                  sender="uwmh.ntua@gmail.com",
                  recipients=[user.email])
    msg.body = f'''To reset your password visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request, ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home_page'))

    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('Instructions have been sent to your email (check spam folder) in order to reset your password.', 'info')
        return redirect(url_for('login_page'))
    return render_template('reset_request.html', title="Reset Password Request", form=form)


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home_page'))

    user = User.verify_reset_token(token)

    if user is None:
        flash('The token is invalid or expired. Please try again.', 'warning')
        return redirect(url_for('reset_request'))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash(f'Your password has been updated!', 'info')
        return redirect(url_for('login_page'))

    return render_template('reset_token.html', title="Reset Password", form=form)


@app.route("/nbs-baseline-assessment", methods=['GET', 'POST'])
@login_required
def nbs_page():
    global load_page_down
    load_page_down = False
    active_site = current_user.site[current_user.active_site]

    # first lets initialize the 2d python list of the problems with the 5 rows containing the default categories
    #if a category doesn't have a concern then the specific row will only contain that one element of the corresponding category
    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    for concern in active_site.ci:
        if concern.category == "Urban":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Environmental":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Social":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Economic/Business":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(concern)

    return render_template('nbs_tool.html', ci_importances=ci_importances, ci_tops=ci_tops, problems=problems,
                            total_ci_counter=total_ci_counter, active_site=active_site, load_page_down=json.dumps(load_page_down),
                           all_ci_ordered=all_ci_ordered)


@app.route("/nbs-preliminary-selection-tool", methods=['GET', 'POST'])
@login_required
def nbs_page_2():
    # MAYBE ONCE SOLUTION IF I GET STUCK IN THE FUTURE IS TO DEPEND THE Nbs_ci both on an NBS and on the corresponding Ci (from the models.py)
    global load_page_down
    load_page_down = False
    active_site = current_user.site[current_user.active_site]

    total_nbs_counter = len(active_site.nbs)

    # first lets initialize the 2d python list of the problems with the 5 rows containing the default categories
    #if a category doesn't have a concern then the specific row will only contain that one element of the corresponding category
    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    all_nbs_ordered = []

    for nbs in active_site.nbs:
        all_nbs_ordered.append(nbs)

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)

    all_nbs_ci_ordered = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Environmental":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Social":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Economic/Business":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            all_nbs_ci_ordered[i][j] = Nbs_ci.query.filter_by(nbs_id=all_nbs_ordered[j].id, ci_id=all_ci_ordered[i].id).first()


    return render_template('nbs_tool_2.html', problems=problems, total_ci_counter=total_ci_counter, active_site=active_site,
                            total_nbs_counter=total_nbs_counter, nbs_cis=nbs_cis, load_page_down=json.dumps(load_page_down),
                           all_ci_ordered=all_ci_ordered, all_nbs_ci_ordered=all_nbs_ci_ordered)


@app.route("/add-concern", methods=['POST'])
@login_required
def add_concern():
    # Since I'm adding a concern, I have to add one more Nbs_ci to all the NBS that exist in the active_site
    active_site = current_user.site[current_user.active_site]

    concern_category = request.form.get("concern_category")
    concern_title = request.form.get("concern_name")

    for concern in active_site.ci: # let's check that the new concern has a unique title
        if concern.title == concern_title:
            flash(f"There is already a concern with that name. The new concern was not added.", "danger")
            return redirect(url_for('nbs_page'))

    new_ci = Ci(category=concern_category, title=concern_title, site_id=active_site.id)
    db.session.add(new_ci)
    db.session.commit()

    for j in range(len(active_site.nbs)):
        new_nbs_ci = Nbs_ci(nbs_id=active_site.nbs[j].id, ci_id=new_ci.id)
        db.session.add(new_nbs_ci)
        db.session.commit()

    flash(f"The new concern has been added!", "info")
    return redirect(url_for('nbs_page'))


@app.route("/rename-concern", methods=['POST'])
@login_required
def rename_concern():
    active_site = current_user.site[current_user.active_site]

    old_concern_title = request.form.get("concern_to_rename")
    new_concern_title = request.form.get("concern_new_name")

    for concern in active_site.ci: # let's check that the new concern has a unique title
        if concern.title == new_concern_title:
            flash(f"There is already a concern with that name.", "danger")
            return redirect(url_for('nbs_page'))

    for i in range(len(active_site.ci)):
        if active_site.ci[i].title == old_concern_title:
            active_site.ci[i].title = new_concern_title
            db.session.commit()
            break

    flash(f"The concern has been renamed!", "info")
    return redirect(url_for('nbs_page'))


@app.route("/remove-concern", methods=['POST'])
@login_required
def remove_concern():
    active_site = current_user.site[current_user.active_site]

    concern_id_to_remove = int(request.form.get("concern_to_remove"))

    concern_to_remove = Ci.query.filter_by(id=concern_id_to_remove).first()
    concern_to_remove_category = concern_to_remove.category

    total_concerns_category = 0 # if there are too few concerns of a specific category, we don't want to let the user completely remove the category
    for concern in active_site.ci:
        if concern.category == concern_to_remove_category:
            total_concerns_category += 1

    if total_concerns_category < 3:
        flash(f"There are too few concerns in category '{concern_to_remove_category}'. The concern was not removed.", "danger")
        return redirect(url_for('nbs_page'))
    else:
        for j in range(len(active_site.nbs)):
            db.session.delete(Nbs_ci.query.filter_by(nbs_id=active_site.nbs[j].id, ci_id=concern_to_remove.id).first())
            db.session.commit()

        db.session.delete(concern_to_remove)
        db.session.commit()

        flash(f"The concern has been removed!", "info")
        return redirect(url_for('nbs_page'))


@app.route("/add-nbs", methods=['POST'])
@login_required
def add_nbs():
    active_site = current_user.site[current_user.active_site]

    new_nbs_title = request.form.get("nbs_name")

    # first let's check that this is indeed a new NBS
    for nbs in active_site.nbs:
        if nbs.title == new_nbs_title:
            flash(f"Please choose a unique NBS name.", "danger")
            return redirect(url_for('nbs_page_2'))

    # if I don't return from the function let's create the new NBS
    new_nbs = Nbs(title=new_nbs_title, site_id=active_site.id)
    db.session.add(new_nbs)
    db.session.commit()

    new_nbs = Nbs.query.filter_by(title=new_nbs_title, site_id=active_site.id).first()

    for i in range(len(active_site.ci)):
        new_nbs_ci = Nbs_ci(nbs_id=new_nbs.id, ci_id=active_site.ci[i].id)
        db.session.add(new_nbs_ci)
        db.session.commit()

    flash(f"The new NBS has been added!", "info")
    return redirect(url_for('nbs_page_2'))


@app.route("/remove-nbs", methods=['POST'])
@login_required
def remove_nbs():
    active_site = current_user.site[current_user.active_site]

    nbs_remove_id = int(request.form.get("nbs_to_remove"))
    nbs_remove = Nbs.query.filter_by(id=nbs_remove_id).first()

    if len(active_site.nbs) == 1:
        flash(f"This site has only one NBS. It can't be deleted.", "danger")
        return redirect(url_for('nbs_page_2'))
    else:
        for i in range(len(active_site.ci)):
            nbs_ci_remove = Nbs_ci.query.filter_by(nbs_id=nbs_remove_id, ci_id=active_site.ci[i].id).first()
            db.session.delete(nbs_ci_remove)
            db.session.commit()

        db.session.delete(nbs_remove)
        db.session.commit()

        flash(f"The requested NBS has been deleted!", "info")
        return redirect(url_for('nbs_page_2'))


@app.route("/nbs-preliminary-selection-tool/active-site", methods=['POST'])
@login_required
def update_active_site():
    new_active_site_title = request.form.get("all-sites")

    for i in range(len(current_user.site)):
        if current_user.site[i].title == new_active_site_title:
            current_user.active_site = i
            db.session.commit()
            break

    flash(f"Active Site: {Site.query.filter_by(title=new_active_site_title).first().title}", "info")
    return redirect(url_for('nbs_page'))


@app.route("/update-active-site-title", methods=['POST'])
@login_required
def update_active_site_title(): # this code section updates the TITLE of the activated Site
    new_title = request.form.get("site_title")

    if len(new_title) < 1:
        flash("You haven't specified a title. Site's title has not changed.", "info")
        return redirect(url_for('nbs_page'))

    for site in current_user.site:
        if site.title == new_title:
            flash(f"This site title already exists.", 'danger')
            return redirect(url_for('nbs_page'))

    current_user.site[current_user.active_site].title = new_title
    db.session.commit()

    flash(f"The site's title has changed!", 'info')
    return redirect(url_for('nbs_page'))


@app.route("/create-new-site", methods=['POST'])
@login_required
def create_new_site():

    # the total concerns will be represented as a 2D python list where each row has as first element each concerns' category
    # and the rest elements of each row refer to the actual concerns of that specific category
    problems = [
        ["Urban", "Accessibility", "Green space per inhabitant", "Multifunctionality"],
        ["Environmental", "Extreme heat", "Water scarcity", "Water quality", "Flooding", "Wastewater treatment",
            "Air quality", "Biodiversity", "Share of green areas"],
        ["Social", "Community engagement", "Access to sport facilities", "Access to cultural facilities",
            "Crime", "Aesthetics", "Quality of experience"],
        ["Economic/Business", "Property value", "Unemployment", "Business activity"],
        ["PH & WB (Public Health & Well Being)", "Chronic respiratory diseases", "Cardiovascular diseases",
            "Diabetes", "Obesity", "Depression", "Physical activity", "Communicable diseases - alimentary infections",
            "Communicable diseases - vector borne diseases"]
                ]

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    new_site_title = request.form.get('site_title')

    for _site in current_user.site: # first lets check that the site has a unique title
        if _site.title == new_site_title:
            flash("This site already exists.", "danger")
            return redirect(url_for('nbs_page'))

    if len(new_site_title) < 1:
        flash("You haven't specified a name for the new site. The site has not been created.", "danger")
        return redirect(url_for('nbs_page'))

    site = Site(title=new_site_title, user_id=current_user.id)
    db.session.add(site)
    db.session.commit()

    site = Site.query.filter_by(title=new_site_title, user_id=current_user.id).first()

    all_info_added = True # just for debuging reasons

    # the user gets all default 28 concerns created automatically for his site when registering to the webpage
    for cat in problems:
        for j in range(1, len(cat)):  # in each list the item 0 refers to the category and the rest elements refer to the actual concerns
            new_ci = Ci(category=cat[0], title=cat[j], site_id=site.id)
            db.session.add(new_ci)
            db.session.commit()

    new_nbs = Nbs(site_id=site.id)
    db.session.add(new_nbs)
    db.session.commit()

    new_nbs = Nbs.query.filter_by(site_id=site.id).first()

    # the user gets automatically gets the default impacts that his one and only NBS has accross all the CIs
    for i in range(len(site.ci)):
        new_nbs_ci = Nbs_ci(nbs_id=new_nbs.id, ci_id=site.ci[i].id)
        db.session.add(new_nbs_ci)
        db.session.commit()

    if all_info_added:
        flash(f'The new site has been created!', 'info')
        for i in range(len(current_user.site)):
            if current_user.site[i].title == new_site_title:
                current_user.active_site = i
                db.session.commit()
                break
        return redirect(url_for('nbs_page'))


@app.route("/delete-site", methods=['POST'])
@login_required
def delete_site():

    site_id = int(request.form.get('all-sites'))

    # I have added one more option "(empty string)" in the deletion menu just so that the user doesn't see his sites ready
    # for deletion and gets frustrated. If he clicks on the 'delete' button with the empty string chosen, a value=-1 gets
    # returned to the backend

    if site_id == -1:
        flash(f"You haven't chosen any site.", 'info')
        return redirect(url_for('nbs_page'))

    if len(current_user.site) == 1: # we can't let the user delete a site if it's the only one he owns
        flash(f"This is your only site, you can't delete it.", 'info')
        return redirect(url_for('nbs_page'))

    site = Site.query.filter_by(id=site_id).first()

    for nbs in site.nbs:
        for nbs_ci in nbs.nbs_ci:
            db.session.delete(nbs_ci) # first i need to delete nbs_ci so that I don't get NOT NULL CONSTRAINT ERRORS
            db.session.commit()

        db.session.delete(nbs)
        db.session.commit()

    for ci in site.ci:
        db.session.delete(ci)
        db.session.commit()

    flash(f"Site named: '{site.title}' is deleted!", 'info')

    db.session.delete(site)
    db.session.commit()

    current_user.active_site = 0 # I change the active site to become the first element in the list, just in case this  is the only one left
    db.session.commit()

    return redirect(url_for('nbs_page'))


@app.route("/update-nbs-data", methods=['POST'])
@login_required
def update_nbs_data():
    global load_page_down

    active_site = current_user.site[current_user.active_site]
    total_top_priorities = 0 # let's make a check for the number of high priorities since we make this loop eitherway

    # first lets initialize the 2d python list of the problems with the 5 rows containing the default categories
    #if a category doesn't have a concern then the specific row will only contain that one element of the corresponding category
    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1
        # I subtract one element from every row of the 2d list to avoid including the categories in the cis

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    for concern in active_site.ci:
        if concern.category == "Urban":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Environmental":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Social":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Economic/Business":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(concern)

    for i in range(total_ci_counter):
        all_ci_ordered[i].importance = request.form.get(f"ci_{i}_importance")
        all_ci_ordered[i].top = request.form.get(f"ci_{i}_top")
        db.session.commit()

        if active_site.ci[i].top == "Yes":
            total_top_priorities += 1
            if (active_site.ci[i].importance == "Moderate Priority") or (active_site.ci[i].importance == "Low Priority") or (active_site.ci[i].importance == "No Problem"):
                flash(f"Concern Importance ---> Element #{i + 1}: Site's top concerns are usually of high priority.", "info")
            elif active_site.ci[i].importance == "Not A Concern":
                flash(f"Concern Importance ---> Element #{i + 1}: A 'Not A Concern' can't be a top priority.", "danger")

    if total_top_priorities > 3:
        flash(f"Please reduce the number of top priorities. (Maximum Top Priorities: 3)", "danger")

    flash(f'Changes have been saved!', 'info')
    load_page_down = True

    # return redirect(url_for('nbs_page'))
    return render_template('nbs_tool.html', ci_importances=ci_importances, ci_tops=ci_tops, problems=problems,
                            total_ci_counter=total_ci_counter, active_site=active_site, load_page_down=json.dumps(load_page_down),
                           all_ci_ordered=all_ci_ordered)


@app.route("/update-nbs-data-2", methods=['POST'])
@login_required
def update_nbs_data_2(): # this is to update the RATIOS AND NAMES of the NBS

    active_site = current_user.site[current_user.active_site]
    total_nbs_counter = len(active_site.nbs)

    for i in range(total_nbs_counter):
        active_site.nbs[i].title = request.form.get(f"nbs{i}_title")
        active_site.nbs[i].ratio = float(request.form.get(f"nbs_{i}_ratio"))

    db.session.commit()
    flash(f'Changes have been saved!', 'info')
    return redirect(url_for('nbs_page_2'))


@app.route("/update-nbs-data-3", methods=['POST'])
@login_required
def update_nbs_data_3():
    global load_page_down

    load_page_down = True

    active_site = current_user.site[current_user.active_site]
    total_nbs_counter = len(active_site.nbs)

    # first lets initialize the 2d python list of the problems with the 5 rows containing the default categories
    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1
        # I subtract one element from every row of the 2d list to avoid including the categories in the cis

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)

    all_nbs_ci_ordered = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Environmental":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Social":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Economic/Business":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            all_nbs_ci_ordered[i][j] = Nbs_ci.query.filter_by(nbs_id=active_site.nbs[j].id, ci_id=all_ci_ordered[i].id).first()

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            all_nbs_ci_ordered[i][j].impact = request.form.get(f"nbs_{j}_ci_{i}")
    db.session.commit()

    flash(f'Changes have been saved!', 'info')
    return render_template('nbs_tool_2.html', problems=problems, total_ci_counter=total_ci_counter, active_site=active_site,
                           total_nbs_counter=total_nbs_counter, nbs_cis=nbs_cis, load_page_down=json.dumps(load_page_down),
                           all_ci_ordered=all_ci_ordered, all_nbs_ci_ordered=all_nbs_ci_ordered)


@app.route("/assess-concerns", methods=['GET'])
@login_required
def results_page():

    active_site = current_user.site[current_user.active_site]

    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    problems_names = []
    for cat in problems:
        for j in range(1, len(cat)):
            problems_names.append(cat[j])

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    for concern in active_site.ci:
        if concern.category == "Urban":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Environmental":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Social":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Economic/Business":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(concern)

    ci_importance = []
    ci_top = []
    top_counter = 0

    for i in range(total_ci_counter):
        if active_site.ci[i].importance == ci_importances[1]:
            ci_importance.append(3)
        elif active_site.ci[i].importance == ci_importances[2]:
            ci_importance.append(2)
        elif active_site.ci[i].importance == ci_importances[3]:
            ci_importance.append(1)
        elif active_site.ci[i].importance == ci_importances[4]:
            ci_importance.append(0)
        elif active_site.ci[i].importance == ci_importances[5]:
            ci_importance.append("Not A Concern")
        elif active_site.ci[i].importance == ci_importances[0]:
            flash(f"Concern Importance ---> Element '{active_site.ci[i].title}' is not filled.", 'danger')
            return redirect(url_for('nbs_page'))

        if active_site.ci[i].top == "Yes":
            ci_top.append(1)
            top_counter += 1
            if top_counter > 3:
                flash('You have set more than 3 top priorities.', 'danger')
                return redirect(url_for('nbs_page'))

            if active_site.ci[i].importance == "Not A Concern":
                flash(f"Concern Importance ---> Element '{active_site.ci[i].title}': A 'Not A Concern' can't be a top priority.", "danger")
                return redirect(url_for('nbs_page'))

        elif active_site.ci[i].top == "No":
            ci_top.append(0)

    # Final manipulation of the data and calculations before rerouting the user to the final webpage of the baseline results

    overall_actual_problem_score = 0
    overall_max_problem_score = 0
    overall_actual_max_percentage = 0

    urban_actual_score = 0
    urban_max_score = 0
    urban_actual_max_percentage = 0
    urban_actual_percentage = 0

    environmental_actual_score = 0
    environmental_max_score = 0
    environmental_actual_max_percentage = 0
    environmental_actual_percentage = 0

    social_actual_score = 0
    social_max_score = 0
    social_actual_max_percentage = 0
    social_actual_percentage = 0

    economic_actual_score = 0
    economic_max_score = 0
    economic_actual_max_percentage = 0
    economic_actual_percentage = 0

    ph_actual_score = 0
    ph_max_score = 0
    ph_actual_max_percentage = 0
    ph_actual_percentage = 0

    for i in range(len(ci_importance)):
        if not isinstance(ci_importance[i], str):
            overall_actual_problem_score += ci_importance[i]
            overall_max_problem_score += 3

            if active_site.ci[i].category == "Urban":
                urban_actual_score += ci_importance[i]
                urban_max_score += 3

            elif active_site.ci[i].category == "Environmental":
                environmental_actual_score += ci_importance[i]
                environmental_max_score += 3

            elif active_site.ci[i].category == "Social":
                social_actual_score += ci_importance[i]
                social_max_score += 3

            elif active_site.ci[i].category == "Economic/Business":
                economic_actual_score += ci_importance[i]
                economic_max_score += 3

            elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
                ph_actual_score += ci_importance[i]
                ph_max_score += 3

    if overall_max_problem_score != 0:
        overall_actual_max_percentage = overall_actual_problem_score / overall_max_problem_score
    else:
        overall_actual_max_percentage = 0

    if urban_max_score != 0:
        urban_actual_max_percentage = urban_actual_score / urban_max_score
    else:
        urban_actual_max_percentage = 0

    if environmental_max_score != 0:
        environmental_actual_max_percentage = environmental_actual_score / environmental_max_score
    else:
        environmental_actual_max_percentage = 0

    if social_max_score != 0:
        social_actual_max_percentage = social_actual_score / social_max_score
    else:
        social_actual_max_percentage = 0

    if economic_max_score != 0:
        economic_actual_max_percentage = economic_actual_score / economic_max_score
    else:
        economic_actual_max_percentage = 0

    if ph_max_score != 0:
        ph_actual_max_percentage = ph_actual_score / ph_max_score
    else:
        ph_actual_max_percentage = 0

    if overall_actual_problem_score != 0:
        urban_actual_percentage = urban_actual_score / overall_actual_problem_score
        environmental_actual_percentage = environmental_actual_score / overall_actual_problem_score
        social_actual_percentage = social_actual_score / overall_actual_problem_score
        economic_actual_percentage = economic_actual_score / overall_actual_problem_score
        ph_actual_percentage = ph_actual_score / overall_actual_problem_score
    else:
        urban_actual_percentage = 0
        environmental_actual_percentage = 0
        social_actual_percentage = 0
        economic_actual_percentage = 0
        ph_actual_percentage = 0

    actual_percentages = [urban_actual_percentage, environmental_actual_percentage, social_actual_percentage,
                          economic_actual_percentage, ph_actual_percentage]

    actual_percentages_100 = [] # just mutliplying the values by 100 in order to pass ready-to-plot values to the frontend

    for element in actual_percentages:
        actual_percentages_100.append(element * 100)

    actual_max_percentages = [urban_actual_max_percentage, environmental_actual_max_percentage, social_actual_max_percentage,
                              economic_actual_max_percentage, ph_actual_max_percentage, overall_actual_max_percentage]

    actual_max_percentages_100 = [] # just mutliplying the values by 100 in order to pass ready-to-plot values to the frontend

    for element in actual_max_percentages:
        actual_max_percentages_100.append(element * 100)

    ci_importance_without_na = [] # this will contain ALL THE CONCERNS ORDERED WITHOUT STRINGS TO PLOT GRAPH 3 IN THE FRONTEND

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance_without_na.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance_without_na.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance_without_na.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance_without_na.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance_without_na.append(0)

    # full_problems will be used from js (that's why I need json) while problems will be used directly from html with jinja syntax
    return render_template('results.html', title="Results", total_ci_counter=total_ci_counter, actual_percentages=actual_percentages,
                           actual_max_percentages=actual_max_percentages, ci_importance_without_na=ci_importance_without_na,
                           ci_importances=ci_importances, ci_tops=ci_tops, problems=problems, active_site=active_site,
                           actual_percentages_100=actual_percentages_100, actual_max_percentages_100=actual_max_percentages_100,
                           problems_names=json.dumps(problems_names), full_problems=json.dumps(problems), all_ci_ordered=all_ci_ordered)


@app.route("/view-nbs-results", methods=['GET'])
@login_required
def results_page_2():

    active_site = current_user.site[current_user.active_site]

    total_nbs_counter = len(active_site.nbs)

    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    problems_names = []
    for cat in problems:
        for j in range(1, len(cat)):
            problems_names.append(cat[j])

    # all_ci_ordered (total_ci_counter,): 1d list containing all the concerns for the active site ORDERED
    # (fist Urban, then Environmental etc.)

    # all_nbs_ordered (total_nbs_counter,): 1d list containing all NBS for the active site ORDERED

    # all_nbs_ci_ordered (total_ci_counter, total_nbs_counter): 2d list containing all impacts of all NBS against
    # all concerns for the active site ORDERED
    # (fist Urban, then Environmental etc. ~ concern-wise and active_cite.nbs[0], active_cite.nbs[1]) etc. ~ nbs-wise)

    # ci_importance (total_ci_counter,): 1d list containing values 0,1,2,3,"Not A Concern" according to the importance
    # of all concerns ORDERED (fist Urban, then Environmental etc.)

    # ci_top (total_ci_counter,): 1d list containing values 0,1 according to whether a concern is a top priority or not
    # for all concerns ORDERED (fist Urban, then Environmental etc.)

    all_nbs_ordered = []

    for nbs in active_site.nbs:
        all_nbs_ordered.append(nbs)

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    all_nbs_ci_ordered = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Environmental":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Social":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Economic/Business":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            all_nbs_ci_ordered[i][j] = Nbs_ci.query.filter_by(nbs_id=all_nbs_ordered[j].id, ci_id=all_ci_ordered[i].id).first()


    ci_importance = [] # this is still unordered
    ci_top = []
    top_counter = 0

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance.append("Not A Concern")
        elif all_ci_ordered[i].importance == ci_importances[0]:
            flash(f"Concern Importance ---> Element '{all_ci_ordered[i].title}' is not filled.", 'danger')
            return redirect(url_for('nbs_page'))

        if all_ci_ordered[i].top == "Yes":
            ci_top.append(1)
            top_counter += 1
            if top_counter > 3:
                flash('You have set more than 3 top priorities.', 'danger')
                return redirect(url_for('nbs_page'))

            if all_ci_ordered[i].importance == "Not A Concern":
                flash(f"Concern Importance ---> Element '{all_ci_ordered[i].title}': A 'Not A Concern' can't be a top priority.", "danger")
                return redirect(url_for('nbs_page'))

        elif all_ci_ordered[i].top == "No":
            ci_top.append(0)

    ci_importance_without_na = [] # this will contain ALL THE CONCERNS ORDERED WITHOUT STRINGS TO PLOT GRAPHS IN THE FRONTEND

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance_without_na.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance_without_na.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance_without_na.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance_without_na.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance_without_na.append(0)


    all_nbs_ci_ordered_impact_value = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if all_nbs_ci_ordered[i][j].impact == nbs_cis[1]:
                all_nbs_ci_ordered_impact_value[i][j] = 1.0
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[2]:
                all_nbs_ci_ordered_impact_value[i][j] = 0.5
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[3]:
                all_nbs_ci_ordered_impact_value[i][j] = 0.0
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[0]:
                flash(f"Impact ==> ('{all_ci_ordered[i].title}' - '{all_nbs_ordered[j].title}') is not filled yet.", "danger")
                return redirect(url_for("nbs_page_2"))


    all_nbs_ci_ordered_impact_with_importances = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if isinstance(ci_importance[i], str):
                all_nbs_ci_ordered_impact_with_importances[i][j] = ci_importance[i] # 'Not A concern'
            else:
                all_nbs_ci_ordered_impact_with_importances[i][j] = all_nbs_ci_ordered_impact_value[i][j] * ci_importance[i]

    # Initializations of all scores

    urban_sum = [0 for i in range(total_nbs_counter)]
    environmental_sum = [0 for i in range(total_nbs_counter)]
    social_sum = [0 for i in range(total_nbs_counter)]
    economic_sum = [0 for i in range(total_nbs_counter)]
    ph_sum = [0 for i in range(total_nbs_counter)]
    overall_sum = [0 for i in range(total_nbs_counter)]

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str):
                overall_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]

            if (all_ci_ordered[i].category == "Urban") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                urban_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Environmental") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                environmental_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Social") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                social_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Economic/Business") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                economic_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "PH & WB (Public Health & Well Being)") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                ph_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]

    urban_sum_importance = 0
    environmental_sum_importance = 0
    social_sum_importance = 0
    economic_sum_importance = 0
    ph_sum_importance = 0
    overall_sum_importance = 0

    for i in range(total_ci_counter):
        if not isinstance(ci_importance[i], str):
            overall_sum_importance += ci_importance[i]

            if all_ci_ordered[i].category == "Urban":
                urban_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Environmental":
                environmental_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Social":
                social_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Economic/Business":
                economic_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "PH & WB (Public Health & Well Being)":
                ph_sum_importance += ci_importance[i]

    urban_scores = [0 for _ in range(total_nbs_counter)]
    environmental_scores = [0 for _ in range(total_nbs_counter)]
    social_scores = [0 for _ in range(total_nbs_counter)]
    economic_scores = [0 for _ in range(total_nbs_counter)]
    ph_scores = [0 for _ in range(total_nbs_counter)]
    overall_scores = [0 for _ in range(total_nbs_counter)]

    if urban_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            urban_scores[i] = (urban_sum[i] / urban_sum_importance) * all_nbs_ordered[i].ratio

    if environmental_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            environmental_scores[i] = (environmental_sum[i] / environmental_sum_importance) * all_nbs_ordered[i].ratio

    if social_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            social_scores[i] = (social_sum[i] / social_sum_importance) * all_nbs_ordered[i].ratio

    if economic_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            economic_scores[i] = (economic_sum[i] / economic_sum_importance) * all_nbs_ordered[i].ratio

    if ph_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            ph_scores[i] = (ph_sum[i] / ph_sum_importance) * all_nbs_ordered[i].ratio

    if overall_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            overall_scores[i] = (overall_sum[i] / overall_sum_importance) * all_nbs_ordered[i].ratio


    final_scores = [urban_scores, environmental_scores, social_scores, economic_scores, ph_scores, overall_scores]

    # Let's Use the Bubblesort sorting algorithm to sort the NBS in descending order according to their overall scores
    # in order to create the second table of the results

    nbs_descending_order = copy.deepcopy(all_nbs_ordered)  # from best to worst
    overall_scores_descending_order = copy.deepcopy(overall_scores)

    for i in range(total_nbs_counter - 1):
        for j in range(total_nbs_counter - i - 1):
            if overall_scores_descending_order[j] < overall_scores_descending_order[j+1]:
                overall_scores_descending_order[j], overall_scores_descending_order[j+1] = overall_scores_descending_order[j+1], overall_scores_descending_order[j]
                nbs_descending_order[j], nbs_descending_order[j+1] = nbs_descending_order[j+1], nbs_descending_order[j]

    nbs_descending_order_against_top = [[] for i in range(total_nbs_counter)]

    for i in range(total_nbs_counter):
        for j in range(total_ci_counter):
            if all_ci_ordered[j].top == "Yes":
                nbs_descending_order_against_top[i].append(Nbs_ci.query.filter_by(nbs_id=nbs_descending_order[i].id, ci_id=all_ci_ordered[j].id).first().impact)


    nbs_names = []
    for nbs in all_nbs_ordered:
        nbs_names.append(nbs.title)


    # this best_solution_index is found in order to make green the bar refering to the best solution in plot 1
    best_solution = max(overall_scores)
    best_solution_index = overall_scores.index(best_solution)


    # In order to plot the final plots (radar-bar charts of all NBS) we need to TRAVERSE two arrays, namely the
    # final_scores 2d array and the all_nbs_ci_ordered_impact_with_importances 2d array

    # The final_scores_traversed 2d list is usefull for the final graphs (2d list with as many rows as the total NBS
    # and each row has all scores for each NBS (urban, environmental, social, economic, ph) EXCEPT THE OVERALL SCORE
    final_scores_traversed = []
    for i in range(total_nbs_counter):
        final_scores_traversed.append([])
        for j in range(len(final_scores) - 1): # we don't want the overall score of the NBS
            final_scores_traversed[i].append(final_scores[j][i] * 100) # let's get the scores % wise

    # Let's traverse the all_nbs_ci_ordered_impact_with_importances array now
    all_nbs_ci_ordered_impact_with_importances_traversed = []
    for i in range(total_nbs_counter):
        all_nbs_ci_ordered_impact_with_importances_traversed.append([])
        for j in range(len(all_nbs_ci_ordered_impact_with_importances)):
            all_nbs_ci_ordered_impact_with_importances_traversed[i].append(all_nbs_ci_ordered_impact_with_importances[j][i])

    # WHEN I PASS DATA FROM FLASK TO BE USED DIRECTLY IN THE HTML THROUGH JINJA (NOT JS) I DON'T USE json.dumps()

    return render_template("results2.html", total_nbs_counter=total_nbs_counter, total_ci_counter=total_ci_counter,
                           ci_importance_without_na=ci_importance_without_na, problems=problems, full_problems=json.dumps(problems),
                           ci_importances=ci_importances, ci_tops=ci_tops, all_ci_ordered=all_ci_ordered,
                           final_scores=final_scores, active_site=active_site, all_nbs_ordered=all_nbs_ordered,
                           nbs_descending_order=nbs_descending_order, overall_scores_descending_order=overall_scores_descending_order,
                           nbs_descending_order_against_top=nbs_descending_order_against_top, top_counter=top_counter,
                           overall_scores=json.dumps(overall_scores), nbs_names=json.dumps(nbs_names), nbs_names_html=nbs_names,
                           best_solution_index=best_solution_index, problems_names=json.dumps(problems_names),
                           all_nbs_ci_ordered_impact_with_importances=json.dumps(all_nbs_ci_ordered_impact_with_importances),
                           all_nbs_ci_ordered_impact_with_importances_traversed=json.dumps(all_nbs_ci_ordered_impact_with_importances_traversed),
                           final_scores_traversed=json.dumps(final_scores_traversed), all_nbs_ci_ordered=all_nbs_ci_ordered)


################################## GENERATE PDFs SECTION ##################################

@app.route("/generate-pdf-1", methods=['GET', 'POST'])
@login_required
def generatePdf1():

    # the logic of this route should be exactly (copy-paste) the logic of the results_page()
    # (only difference is at the end ~ I don't return render_template, I instead rendered = render_template and 3 more lines of code at the end)
    # and I don't render the results.html, I render the results_pdf.html (the html pages differentiate slightly)
    # in order to get the results, but I will render a different html page just to remove the navigation bar and things like that
    # so that it can look more like a pdf report and less like a webpage

    active_site = current_user.site[current_user.active_site]

    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    problems_names = []
    for cat in problems:
        for j in range(1, len(cat)):
            problems_names.append(cat[j])

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    for concern in active_site.ci:
        if concern.category == "Urban":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Environmental":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Social":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "Economic/Business":
            all_ci_ordered.append(concern)
    for concern in active_site.ci:
        if concern.category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(concern)

    ci_importance = []
    ci_top = []
    top_counter = 0

    for i in range(total_ci_counter):
        if active_site.ci[i].importance == ci_importances[1]:
            ci_importance.append(3)
        elif active_site.ci[i].importance == ci_importances[2]:
            ci_importance.append(2)
        elif active_site.ci[i].importance == ci_importances[3]:
            ci_importance.append(1)
        elif active_site.ci[i].importance == ci_importances[4]:
            ci_importance.append(0)
        elif active_site.ci[i].importance == ci_importances[5]:
            ci_importance.append("Not A Concern")
        elif active_site.ci[i].importance == ci_importances[0]:
            flash(f"Concern Importance ---> Element '{active_site.ci[i].title}' is not filled.", 'danger')
            return redirect(url_for('nbs_page'))

        if active_site.ci[i].top == "Yes":
            ci_top.append(1)
            top_counter += 1
            if top_counter > 3:
                flash('You have set more than 3 top priorities.', 'danger')
                return redirect(url_for('nbs_page'))

            if active_site.ci[i].importance == "Not A Concern":
                flash(f"Concern Importance ---> Element '{active_site.ci[i].title}': A 'Not A Concern' can't be a top priority.", "danger")
                return redirect(url_for('nbs_page'))

        elif active_site.ci[i].top == "No":
            ci_top.append(0)

    # Final manipulation of the data and calculations before rerouting the user to the final webpage of the baseline results

    overall_actual_problem_score = 0
    overall_max_problem_score = 0
    overall_actual_max_percentage = 0

    urban_actual_score = 0
    urban_max_score = 0
    urban_actual_max_percentage = 0
    urban_actual_percentage = 0

    environmental_actual_score = 0
    environmental_max_score = 0
    environmental_actual_max_percentage = 0
    environmental_actual_percentage = 0

    social_actual_score = 0
    social_max_score = 0
    social_actual_max_percentage = 0
    social_actual_percentage = 0

    economic_actual_score = 0
    economic_max_score = 0
    economic_actual_max_percentage = 0
    economic_actual_percentage = 0

    ph_actual_score = 0
    ph_max_score = 0
    ph_actual_max_percentage = 0
    ph_actual_percentage = 0

    for i in range(len(ci_importance)):
        if not isinstance(ci_importance[i], str):
            overall_actual_problem_score += ci_importance[i]
            overall_max_problem_score += 3

            if active_site.ci[i].category == "Urban":
                urban_actual_score += ci_importance[i]
                urban_max_score += 3

            elif active_site.ci[i].category == "Environmental":
                environmental_actual_score += ci_importance[i]
                environmental_max_score += 3

            elif active_site.ci[i].category == "Social":
                social_actual_score += ci_importance[i]
                social_max_score += 3

            elif active_site.ci[i].category == "Economic/Business":
                economic_actual_score += ci_importance[i]
                economic_max_score += 3

            elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
                ph_actual_score += ci_importance[i]
                ph_max_score += 3

    if overall_max_problem_score != 0:
        overall_actual_max_percentage = overall_actual_problem_score / overall_max_problem_score
    else:
        overall_actual_max_percentage = 0

    if urban_max_score != 0:
        urban_actual_max_percentage = urban_actual_score / urban_max_score
    else:
        urban_actual_max_percentage = 0

    if environmental_max_score != 0:
        environmental_actual_max_percentage = environmental_actual_score / environmental_max_score
    else:
        environmental_actual_max_percentage = 0

    if social_max_score != 0:
        social_actual_max_percentage = social_actual_score / social_max_score
    else:
        social_actual_max_percentage = 0

    if economic_max_score != 0:
        economic_actual_max_percentage = economic_actual_score / economic_max_score
    else:
        economic_actual_max_percentage = 0

    if ph_max_score != 0:
        ph_actual_max_percentage = ph_actual_score / ph_max_score
    else:
        ph_actual_max_percentage = 0

    if overall_actual_problem_score != 0:
        urban_actual_percentage = urban_actual_score / overall_actual_problem_score
        environmental_actual_percentage = environmental_actual_score / overall_actual_problem_score
        social_actual_percentage = social_actual_score / overall_actual_problem_score
        economic_actual_percentage = economic_actual_score / overall_actual_problem_score
        ph_actual_percentage = ph_actual_score / overall_actual_problem_score
    else:
        urban_actual_percentage = 0
        environmental_actual_percentage = 0
        social_actual_percentage = 0
        economic_actual_percentage = 0
        ph_actual_percentage = 0

    actual_percentages = [urban_actual_percentage, environmental_actual_percentage, social_actual_percentage,
                          economic_actual_percentage, ph_actual_percentage]

    actual_percentages_100 = [] # just mutliplying the values by 100 in order to pass ready-to-plot values to the frontend

    for element in actual_percentages:
        actual_percentages_100.append(element * 100)

    actual_max_percentages = [urban_actual_max_percentage, environmental_actual_max_percentage, social_actual_max_percentage,
                              economic_actual_max_percentage, ph_actual_max_percentage, overall_actual_max_percentage]

    actual_max_percentages_100 = [] # just mutliplying the values by 100 in order to pass ready-to-plot values to the frontend

    for element in actual_max_percentages:
        actual_max_percentages_100.append(element * 100)

    ci_importance_without_na = [] # this will contain ALL THE CONCERNS ORDERED WITHOUT STRINGS TO PLOT GRAPH 3 IN THE FRONTEND

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance_without_na.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance_without_na.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance_without_na.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance_without_na.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance_without_na.append(0)

    # full_problems will be used from js (that's why I need json) while problems will be used directly from html with jinja syntax
    rendered = render_template('results_pdf.html', title="Results", total_ci_counter=total_ci_counter, actual_percentages=actual_percentages,
                           actual_max_percentages=actual_max_percentages, ci_importance_without_na=ci_importance_without_na,
                           ci_importances=ci_importances, ci_tops=ci_tops, problems=problems, active_site=active_site,
                           actual_percentages_100=actual_percentages_100, actual_max_percentages_100=actual_max_percentages_100,
                           problems_names=json.dumps(problems_names), full_problems=json.dumps(problems), all_ci_ordered=all_ci_ordered)

    pdf = pdfkit.from_string(rendered, False, configuration=config, options = {"enable-local-file-access": None,"quiet": ""})
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=Problems_Report.pdf' # we can also use 'inline'
    return response


@app.route("/generate-pdf-2", methods=['GET', 'POST'])
@login_required
def generatePdf2():

    # the logic of this route should be exactly (copy-paste) the logic of the results_page_2()
    # (only difference is at the end ~ I don't return render_template, I instead rendered = render_template and 3 more lines of code at the end)
    # and I don't render the results2.html, I render the results2_pdf.html (the html pages differentiate slightly)
    # in order to get the results, but I will render a different html page just to remove the navigation bar and things like that
    # so that it can look more like a pdf report and less like a webpage

    active_site = current_user.site[current_user.active_site]

    total_nbs_counter = len(active_site.nbs)

    problems = [["Urban"], ["Environmental"], ["Social"], ["Economic/Business"], ["PH & WB (Public Health & Well Being)"]]

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            problems[0].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Environmental":
            problems[1].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Social":
            problems[2].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "Economic/Business":
            problems[3].append(active_site.ci[i].title)
        elif active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            problems[4].append(active_site.ci[i].title)

    total_ci_counter = 0
    for category in problems:
        total_ci_counter += len(category) - 1

    problems_names = []
    for cat in problems:
        for j in range(1, len(cat)):
            problems_names.append(cat[j])

    # all_ci_ordered (total_ci_counter,): 1d list containing all the concerns for the active site ORDERED
    # (fist Urban, then Environmental etc.)

    # all_nbs_ordered (total_nbs_counter,): 1d list containing all NBS for the active site ORDERED

    # all_nbs_ci_ordered (total_ci_counter, total_nbs_counter): 2d list containing all impacts of all NBS against
    # all concerns for the active site ORDERED
    # (fist Urban, then Environmental etc. ~ concern-wise and active_cite.nbs[0], active_cite.nbs[1]) etc. ~ nbs-wise)

    # ci_importance (total_ci_counter,): 1d list containing values 0,1,2,3,"Not A Concern" according to the importance
    # of all concerns ORDERED (fist Urban, then Environmental etc.)

    # ci_top (total_ci_counter,): 1d list containing values 0,1 according to whether a concern is a top priority or not
    # for all concerns ORDERED (fist Urban, then Environmental etc.)

    all_nbs_ordered = []

    for nbs in active_site.nbs:
        all_nbs_ordered.append(nbs)

    all_ci_ordered = [] # 1d python list containing all the concerns ORDERED (first all Urban, then Environmental etc.)
    all_nbs_ci_ordered = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Urban":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Environmental":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Social":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "Economic/Business":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(len(active_site.ci)):
        if active_site.ci[i].category == "PH & WB (Public Health & Well Being)":
            all_ci_ordered.append(active_site.ci[i])

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            all_nbs_ci_ordered[i][j] = Nbs_ci.query.filter_by(nbs_id=all_nbs_ordered[j].id, ci_id=all_ci_ordered[i].id).first()


    ci_importance = [] # this is still unordered
    ci_top = []
    top_counter = 0

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance.append("Not A Concern")
        elif all_ci_ordered[i].importance == ci_importances[0]:
            flash(f"Concern Importance ---> Element '{all_ci_ordered[i].title}' is not filled.", 'danger')
            return redirect(url_for('nbs_page'))

        if all_ci_ordered[i].top == "Yes":
            ci_top.append(1)
            top_counter += 1
            if top_counter > 3:
                flash('You have set more than 3 top priorities.', 'danger')
                return redirect(url_for('nbs_page'))

            if all_ci_ordered[i].importance == "Not A Concern":
                flash(f"Concern Importance ---> Element '{all_ci_ordered[i].title}': A 'Not A Concern' can't be a top priority.", "danger")
                return redirect(url_for('nbs_page'))

        elif all_ci_ordered[i].top == "No":
            ci_top.append(0)

    ci_importance_without_na = [] # this will contain ALL THE CONCERNS ORDERED WITHOUT STRINGS TO PLOT GRAPHS IN THE FRONTEND

    for i in range(total_ci_counter):
        if all_ci_ordered[i].importance == ci_importances[1]:
            ci_importance_without_na.append(3)
        elif all_ci_ordered[i].importance == ci_importances[2]:
            ci_importance_without_na.append(2)
        elif all_ci_ordered[i].importance == ci_importances[3]:
            ci_importance_without_na.append(1)
        elif all_ci_ordered[i].importance == ci_importances[4]:
            ci_importance_without_na.append(0)
        elif all_ci_ordered[i].importance == ci_importances[5]:
            ci_importance_without_na.append(0)


    all_nbs_ci_ordered_impact_value = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if all_nbs_ci_ordered[i][j].impact == nbs_cis[1]:
                all_nbs_ci_ordered_impact_value[i][j] = 1.0
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[2]:
                all_nbs_ci_ordered_impact_value[i][j] = 0.5
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[3]:
                all_nbs_ci_ordered_impact_value[i][j] = 0.0
            elif all_nbs_ci_ordered[i][j].impact == nbs_cis[0]:
                flash(f"Impact ==> ('{all_ci_ordered[i].title}' - '{all_nbs_ordered[j].title}') is not filled yet.", "danger")
                return redirect(url_for("nbs_page_2"))


    all_nbs_ci_ordered_impact_with_importances = [[0] * total_nbs_counter for i in range(total_ci_counter)] # initialization

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if isinstance(ci_importance[i], str):
                all_nbs_ci_ordered_impact_with_importances[i][j] = ci_importance[i] # 'Not A concern'
            else:
                all_nbs_ci_ordered_impact_with_importances[i][j] = all_nbs_ci_ordered_impact_value[i][j] * ci_importance[i]

    # Initializations of all scores

    urban_sum = [0 for i in range(total_nbs_counter)]
    environmental_sum = [0 for i in range(total_nbs_counter)]
    social_sum = [0 for i in range(total_nbs_counter)]
    economic_sum = [0 for i in range(total_nbs_counter)]
    ph_sum = [0 for i in range(total_nbs_counter)]
    overall_sum = [0 for i in range(total_nbs_counter)]

    for i in range(total_ci_counter):
        for j in range(total_nbs_counter):
            if not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str):
                overall_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]

            if (all_ci_ordered[i].category == "Urban") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                urban_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Environmental") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                environmental_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Social") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                social_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "Economic/Business") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                economic_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]
            elif (all_ci_ordered[i].category == "PH & WB (Public Health & Well Being)") and (not isinstance(all_nbs_ci_ordered_impact_with_importances[i][j], str)):
                ph_sum[j] += all_nbs_ci_ordered_impact_with_importances[i][j]

    urban_sum_importance = 0
    environmental_sum_importance = 0
    social_sum_importance = 0
    economic_sum_importance = 0
    ph_sum_importance = 0
    overall_sum_importance = 0

    for i in range(total_ci_counter):
        if not isinstance(ci_importance[i], str):
            overall_sum_importance += ci_importance[i]

            if all_ci_ordered[i].category == "Urban":
                urban_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Environmental":
                environmental_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Social":
                social_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "Economic/Business":
                economic_sum_importance += ci_importance[i]
            elif all_ci_ordered[i].category == "PH & WB (Public Health & Well Being)":
                ph_sum_importance += ci_importance[i]

    urban_scores = [0 for _ in range(total_nbs_counter)]
    environmental_scores = [0 for _ in range(total_nbs_counter)]
    social_scores = [0 for _ in range(total_nbs_counter)]
    economic_scores = [0 for _ in range(total_nbs_counter)]
    ph_scores = [0 for _ in range(total_nbs_counter)]
    overall_scores = [0 for _ in range(total_nbs_counter)]

    if urban_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            urban_scores[i] = (urban_sum[i] / urban_sum_importance) * all_nbs_ordered[i].ratio

    if environmental_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            environmental_scores[i] = (environmental_sum[i] / environmental_sum_importance) * all_nbs_ordered[i].ratio

    if social_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            social_scores[i] = (social_sum[i] / social_sum_importance) * all_nbs_ordered[i].ratio

    if economic_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            economic_scores[i] = (economic_sum[i] / economic_sum_importance) * all_nbs_ordered[i].ratio

    if ph_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            ph_scores[i] = (ph_sum[i] / ph_sum_importance) * all_nbs_ordered[i].ratio

    if overall_sum_importance != 0: # else all the list is initialized with 0
        for i in range(total_nbs_counter):
            overall_scores[i] = (overall_sum[i] / overall_sum_importance) * all_nbs_ordered[i].ratio


    final_scores = [urban_scores, environmental_scores, social_scores, economic_scores, ph_scores, overall_scores]

    # Let's Use the Bubblesort sorting algorithm to sort the NBS in descending order according to their overall scores
    # in order to create the second table of the results

    nbs_descending_order = copy.deepcopy(all_nbs_ordered)  # from best to worst
    overall_scores_descending_order = copy.deepcopy(overall_scores)

    for i in range(total_nbs_counter - 1):
        for j in range(total_nbs_counter - i - 1):
            if overall_scores_descending_order[j] < overall_scores_descending_order[j+1]:
                overall_scores_descending_order[j], overall_scores_descending_order[j+1] = overall_scores_descending_order[j+1], overall_scores_descending_order[j]
                nbs_descending_order[j], nbs_descending_order[j+1] = nbs_descending_order[j+1], nbs_descending_order[j]

    nbs_descending_order_against_top = [[] for i in range(total_nbs_counter)]

    for i in range(total_nbs_counter):
        for j in range(total_ci_counter):
            if all_ci_ordered[j].top == "Yes":
                nbs_descending_order_against_top[i].append(Nbs_ci.query.filter_by(nbs_id=nbs_descending_order[i].id, ci_id=all_ci_ordered[j].id).first().impact)

    nbs_names = []
    for nbs in all_nbs_ordered:
        nbs_names.append(nbs.title)


    # this best_solution_index is found in order to make green the bar refering to the best solution in plot 1
    best_solution = max(overall_scores)
    best_solution_index = overall_scores.index(best_solution)


    # In order to plot the final plots (radar-bar charts of all NBS) we need to TRAVERSE two arrays, namely the
    # final_scores 2d array and the all_nbs_ci_ordered_impact_with_importances 2d array

    # The final_scores_traversed 2d list is usefull for the final graphs (2d list with as many rows as the total NBS
    # and each row has all scores for each NBS (urban, environmental, social, economic, ph) EXCEPT THE OVERALL SCORE
    final_scores_traversed = []
    for i in range(total_nbs_counter):
        final_scores_traversed.append([])
        for j in range(len(final_scores) - 1): # we don't want the overall score of the NBS
            final_scores_traversed[i].append(final_scores[j][i] * 100) # let's get the scores % wise

    # Let's traverse the all_nbs_ci_ordered_impact_with_importances array now
    all_nbs_ci_ordered_impact_with_importances_traversed = []
    for i in range(total_nbs_counter):
        all_nbs_ci_ordered_impact_with_importances_traversed.append([])
        for j in range(len(all_nbs_ci_ordered_impact_with_importances)):
            all_nbs_ci_ordered_impact_with_importances_traversed[i].append(all_nbs_ci_ordered_impact_with_importances[j][i])


    # WHEN I PASS DATA FROM FLASK TO BE USED DIRECTLY IN THE HTML THROUGH JINJA (NOT JS) I DON'T USE json.dumps()

    rendered = render_template("results2_pdf.html", total_nbs_counter=total_nbs_counter, total_ci_counter=total_ci_counter,
                           ci_importance_without_na=ci_importance_without_na, problems=problems, full_problems=json.dumps(problems),
                           ci_importances=ci_importances, ci_tops=ci_tops, all_ci_ordered=all_ci_ordered,
                           final_scores=final_scores, active_site=active_site, all_nbs_ordered=all_nbs_ordered,
                           nbs_descending_order=nbs_descending_order, overall_scores_descending_order=overall_scores_descending_order,
                           nbs_descending_order_against_top=nbs_descending_order_against_top, top_counter=top_counter,
                           overall_scores=json.dumps(overall_scores), nbs_names_html=nbs_names,
                           best_solution_index=best_solution_index, problems_names=json.dumps(problems_names),
                           all_nbs_ci_ordered=all_nbs_ci_ordered,
                           all_nbs_ci_ordered_impact_with_importances=all_nbs_ci_ordered_impact_with_importances)

    pdf = pdfkit.from_string(rendered, False, configuration=config, options = {
            "enable-local-file-access": None,
            "quiet": ""
        })

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=NBS_Report.pdf' # we can also use 'attachment'
    return response
