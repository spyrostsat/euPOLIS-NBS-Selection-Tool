from nbs_tool import db, login_manager, app
from flask_login import UserMixin
from itsdangerous import URLSafeTimedSerializer as Serializer

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True) # the primary key gets inserted automatically
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    active_site = db.Column(db.Integer, nullable=False,  default=0)
    # when I create a user, he gets automatically one Site, which will be located in the index 0 of the current_user.site list,
    # so the active_site has a default value of 0

    site = db.relationship('Site', backref='user', lazy=True)

    def __repr__(self):
        return f"User('{self.username}')"

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return User.query.get(user_id)


class Site(db.Model): # each user will have 1 row of this Table, which will be the NAME of the site
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False,  default='New Site')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    ci = db.relationship('Ci', backref='site', lazy=True)
    nbs = db.relationship('Nbs', backref='site', lazy=True)

    def __repr__(self):
        return f"Site('{self.title}')"


class Ci(db.Model): # each user will have 27 rows of this Table FOR EVERY SITE, since there are 27 CIs
    # Main Contextual Inticators (CI) importance section
    # these are the titles of the main concerns for each site, e.g. pedestrian accessibility
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(200), nullable=False, default='New Concern')
    importance = db.Column(db.String(20), nullable=False,  default='None Chosen')
    top = db.Column(db.String(20), nullable=False,  default='No')

    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)

    nbs_ci = db.relationship('Nbs_ci', backref='ci', lazy=True)

    def __repr__(self):
        return f"Ci('{self.title}')"


class Nbs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False,  default='New NBS')
    ratio = db.Column(db.Float, nullable=False, default=1.0)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)

    nbs_ci = db.relationship('Nbs_ci', backref='nbs', lazy=True)

    def __repr__(self):
        return f"Nbs('{self.title}')"


class Nbs_ci(db.Model): # each user will have 27 rows of this Table for every site
    # total choises are: 1) direct, 2) indirect, 3) no, 4) none_chosen ~ default
    id = db.Column(db.Integer, primary_key=True)
    impact = db.Column(db.String(20), nullable=False,  default='None Chosen')
    nbs_id = db.Column(db.Integer, db.ForeignKey('nbs.id'), nullable=False)
    ci_id = db.Column(db.Integer, db.ForeignKey('ci.id'), nullable=False)

    def __repr__(self):
        return f"Nbs_ci('{self.impact}')"
