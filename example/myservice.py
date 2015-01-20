import OpenSSL
import hmac
import hashlib
from binascii import hexlify
from datetime import datetime, timedelta
from flask import Flask, abort, render_template
from flask_sqlalchemy import SQLAlchemy
from oauth2devices import OAuth2DevicesProvider

app = Flask(__name__)
app.config.update({
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///db.sqlite',
})
db = SQLAlchemy(app)
oauth = OAuth2DevicesProvider(app)

AUTH_EXPIRATION_TIME = 3600
OUR_KEY = 'ourbigbadkey'

@app.route('/oauth/device', methods=['POST'])
@oauth.code_handler("https://api.example.com/oauth/device/authorize", "https://example.com/activate", 600, 600)
def code():
    return None

@app.route('/oauth/device/authorize', methods=['POST'])
@oauth.authorize_handler()
def authorize():
    return None


@app.route('/activate', methods=['GET', 'POST'])
def authorize_view():

    # CSRF verification
    if request.method == "POST":
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            abort(403)

    auth_code = authcodegetter(request.args.get('auth_code'))

    if auth_code is None or auth_code.expires < datetime.utcnow():
        raise OAuth2Exception(
            'Invalid authorization code',
            type='invalid_request'
        )

    # public is our default scope in this case
    if request.args.get('scopes') is None:
        scopes = ['public']
    else:
        scopes = data.get('scopes').split()

    # scope validation here
    
    # permissions check here

    return render_template('auth_code_authorize.html',
                            cur_user=current_user(),
                            scopes=scopes,
                            app=auth_code.client_id)


@app.route('/activate', methods=['GET', 'POST'])
def confirm_view():
    
    # public is our default scope in this case
    if request.args.get('scopes') is None:
        scopes = ['public']
    else:
        scopes = data.get('scopes').split()

    if data.get('client_id') is None or request.user is None:
        raise OAuth2Exception(
            'missing values for view',
            type='server_error'
        )

    app = clientgetter(data.get('client_id'))

    if app is None:
        raise OAuth2Exception(
            'missing app',
            type='server_error'
        )

    auth_code = authcodegetter(data.get('auth_code'))

    if auth_code is None:
        raise OAuth2Exception(
            'auth code must be sent',
            type='invalid_request'
        )

    auth_code._is_active = True

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True)

class Client(db.Model):
    client_id = db.Column(db.String(40), primary_key=True)
    client_secret = db.Column(db.String(55), nullable=False)

    user_id = db.Column(db.ForeignKey('user.id'))
    user = db.relationship('User')

    _redirect_uris = db.Column(db.Text)
    _default_scopes = db.Column(db.Text)

    @property
    def client_type(self):
        return 'public'

    @property
    def redirect_uris(self):
        if self._redirect_uris:
            return self._redirect_uris.split()
        return []

    @property
    def default_redirect_uri(self):
        return self.redirect_uris[0]

    @property
    def default_scopes(self):
        if self._default_scopes:
            return self._default_scopes.split()
        return []

class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.String(40), db.ForeignKey('client.client_id'),
        nullable=False,
    )
    client = db.relationship('Client')

    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id')
    )
    user = db.relationship('User')

    # currently only bearer is supported
    token_type = db.Column(db.String(40))

    access_token = db.Column(db.String(255))
    refresh_token = db.Column(db.String(255))
    expires = db.Column(db.DateTime)
    created = db.Column(db.DateTime)
    _scopes = db.Column(db.Text)

    @property
    def scopes(self):
        if self._scopes:
            return self._scopes.split()
        return []

    def create_access_token(self, client_id, user_id, scope, token_type):

        expires_in = AUTH_EXPIRATION_TIME
        expires = datetime.utcnow() + timedelta(seconds=expires_in)
        created = datetime.utcnow()

        tok = Token(
            client_id=client_id,
            user_id=user_id,
            access_token=None,
            refresh_token=None,
            token_type=token_type,
            _scopes = ("public private" if scope is None else ' '.join(scope)),
            expires=expires,
            created=created,
        )

        if tok.access_token is None:
            tok.access_token = tok._generate_token()

        db.session.add(tok)
        db.session.commit()
        return tok

    def refresh(self, token):

        tok = Token(
            client_id=self.client_id,
            user_id=self.user_id,
            access_token=self.access_token,
            refresh_token=None,
            token_type=token_type,
            _scopes = ("public private" if scope is None else ' '.join(scope)),
            expires=expires,
            created=created,
        )

        if tok.refresh_token is None:
            tok.refresh_token = tok._generate_refresh_token()

        db.session.add(tok)
        db.session.commit()
        return tok

    def _generate_token(self):
        return hashlib.sha1("app:" + str(self.client_id) + ":user:" + str(self.user_id) + str(hexlify(OpenSSL.rand.bytes(10)))).hexdigest()

    def _generate_refresh_token(self):
        return hashlib.sha1("app:" + str(self.client_id) + ":user:" + str(self.user_id) + ":access_token:" + str(self.id)).hexdigest()

    def contains_scope(scope):
        return scope in self.scope.split(' ')

class Code(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.String(40), db.ForeignKey('client.client_id'),
        nullable=False,
    )
    client = db.relationship('Client')

    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id')
    )
    user = db.relationship('User')

    code = db.Column(db.String(40), unique=True)
    _scopes = db.Column(db.Text)
    expires = db.Column(db.DateTime)
    created = db.Column(db.DateTime)
    _is_active = db.Column(db.Integer)

    @property
    def scopes(self):
        if self._scopes:
            return self._scopes.split()
        return []

    @property
    def is_active(self):
        if self._is_active:
            return True
        else:
            return False

    def generate_new_code(self, client_id):
        return hashlib.sha1("secret:" + client_id + ":req:" + str(hexlify(OpenSSL.rand.bytes(10)))).hexdigest()

    def get_device_code(self):
        return hmac.new(OUR_KEY, "secret:"+str(self.id), hashlib.sha1).hexdigest()

    def exchange_for_access_token(self, app):
        return Token().create_access_token(app.client_id, app.user_id, app.scopes, "grant_auth_code")

def current_user():
    if 'id' in session:
        uid = session['id']
        return User.query.get(uid)
    return None

@oauth.clientgetter
def load_client(client_id):
    return Client.query.filter_by(client_id=client_id).first()

@oauth.authcodesetter
def save_auth_code(code, client_id, user_id, *args, **kwargs):
    codes = Code.query.filter_by(
        client_id=client_id,
        user_id=user_id
    )

    # make sure that every client has only one code connected to a user
    for c in codes:
        db.session.delete(c)

    expires_in = (AUTH_EXPIRATION_TIME if code is None else code.pop('expires_in'))
    expires = datetime.utcnow() + timedelta(seconds=expires_in)
    created = datetime.utcnow()

    cod = Code(
        client_id=client_id,
        user_id=user_id,
        code = (None if code is None else code['code']),
        _scopes = ('public private' if code is None else code['scope']),
        expires=expires,
        created=created,
        _is_active=False
    )

    if cod.code is None:
        cod.code = cod.generate_new_code(cod.client_id)[:8]

    db.session.add(cod)
    db.session.commit()
    return cod

@oauth.authcodegetter
def load_auth_code(code):
    return Code.query.filter_by(code=code).first()

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
