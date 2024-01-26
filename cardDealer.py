import random
from threading import Thread, Lock
from flask import *
from flask_socketio import *
from flask_sqlalchemy import *
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import json
#waitress-serve --host 127.0.0.1 cardDealer:app

app = Flask(__name__, static_url_path="/static")
app.config['SECRET_KEY'] = 'tuesdaysgone'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

users = []
idList = []
count = 0
endOfRound = 0
betsRecieved = 0
cardTotal = 0
dealerCardTotal = 0
splitCheck = False
mutex = Lock()

####Database Creation####
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(15), nullable=False)
    money = db.Column(db.Integer)
    bets = db.Column(db.Integer)
    hands = db.relationship('Hands', backref='user')


class Hands(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    cards = db.relationship('Cards', backref='hands')


class Cards(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crank = db.Column(db.String(15), nullable=False)
    csuit = db.Column(db.String(15), nullable=False)
    imageSrc = db.Column(db.String(30), nullable=False)
    dealt = db.Column(db.Integer)
    hand_id = db.Column(db.Integer, db.ForeignKey('hands.id'))

####Login Manager and Loader####
login_manager = LoginManager(app)
login_manager.init_app(app)
@login_manager.user_loader
def load_user(uid):
    user = User.query.get(uid)
    return user

####Socket Connections and Functions####
@socketio.on('connect')
def connect():
    print("connected")

@socketio.on('disconnect')
def whatever():
    print("disconnected")
    global betsRecieved
    disSid = request.sid
    betsRecieved -= 1
    if disSid in users:
        if disSid == users[count]:
            socketio.emit('disSave', help=disSid)
        users.remove(disSid)
    print("user left:", disSid, "\n")

@socketio.on('join')
def join():
    idList.append(current_user.id)
    sId = request.sid
    users.append(sId)
    print("User Id:", sId, "\n")
    userCash = User.query.filter_by(id=current_user.id).first()
    playerMoney = userCash.money
    userId = str(current_user)
    socketio.emit('playerMoney',data=(playerMoney,userId))

@socketio.on('round')
def robin():
    global count
    global endOfRound
    endOfRound += 1
    count += 1
    count %= len(users)
    if endOfRound >= len(users):
        dealerLog()
    else:
        turn = users[count]
        socketio.emit('next', 'next', room=turn)


####Betting####
@socketio.on('betting')
def bets(data):
    shuffle()
    mutex.acquire()
    try:
        global betsRecieved
        cashAmount = int(data)
        userCash = User.query.filter_by(id=current_user.id).first()
        if cashAmount > userCash.money:
            socketio.emit('badBet', room=users[count])
        else:
            userCash.bets = data
            betsRecieved += 1
            db.session.commit()
        if betsRecieved == len(users):
            for i in range(len(users)):
                socketio.emit('goodBet', room=users[i])
            socketio.emit('dealerDraw')
            socketio.emit('starter', room=users[count])
    finally:
        mutex.release()

####Card Dealing####
@socketio.on('doubleCards')
def twoCard():
    mutex.acquire()
    try:
        global count,cardTotal,splitCheck
        print("requesting card")
        cardList = []
        turn = users[count]
        cardList = []
        splitRanks = []
        hand = Hands.query.filter_by(user_id=current_user.id).first()
        for i in range(2):
            deck = Cards.query.filter_by(dealt=0).all()
            if len(deck) > 0:
                card = random.choice(deck)
                card.dealt = 1
                card.hand_id = hand.id
                rank = card.crank
                if rank == 'jack':
                    rank = 10
                elif rank == 'queen':
                    rank = 10
                elif rank == 'king':
                    rank = 10
                elif rank == 'ace':
                    if cardTotal >= 11:
                        rank = 1
                    elif cardTotal < 11:
                        rank = 11
                cardTotal += int(rank)
                db.session.commit()
                cardList.append({'image': card.imageSrc})
                splitRanks.append(card.crank)
            else:
                shuffle()
                print("need to reshuffle")
    
        if splitRanks[0] == "jack" or splitRanks[0] == "queen" or splitRanks[0] == "king":
            if splitRanks[1] == "jack" or splitRanks[1] == "queen" or splitRanks[1] == "king":
                socketio.emit('splitter', room=turn)
                splitCheck = True

        print("Total: " + str(cardTotal))
        newDeal = json.dumps(cardList)
        userId = str(current_user)
        name = str(current_user.username)
        socketio.emit('cardDisplay', data=(newDeal, userId, name, cardTotal))
        count += 1
        count %= len(users)
    finally:
        mutex.release()

@socketio.on('singleCard')
def hit():
    deck = Cards.query.filter_by(dealt=0).all()
    turn = users[count]
    global cardTotal
    if len(deck) > 0:
        card = random.choice(deck)
        card.dealt = 1
        rank = card.crank
        if rank == 'jack':
            rank = 10
        elif rank == 'queen':
            rank = 10
        elif rank == 'king':
            rank = 10
        elif rank == 'ace':
            if cardTotal >= 11:
                rank = 1
            elif cardTotal < 11:
                rank = 11
        cardTotal += int(rank)
        print("Total: " + str(cardTotal))

        hitDeal = {'image': card.imageSrc}
        newHit = json.dumps(hitDeal)
        userId = str(current_user)
        print(userId)
        name = str(current_user.username)

        playerHand = Hands.query.filter_by(user_id=current_user.id).all()
        if users[count] == users[count - 1] and count != 0:
            card.hand_id = playerHand[1].id
            userId = userId + ".1"
            socketio.emit('hitDisplay', data=(newHit, userId, name,cardTotal))
        else:
            card.hand_id = playerHand[0].id
            socketio.emit('hitDisplay', data=(newHit, userId, name, cardTotal))

        db.session.commit()
    else:
        shuffle()
        print("need to reshuffle")
    if cardTotal > 21:
        print("burst")
        burst()
    if cardTotal == 21:
        endgame()

@socketio.on('dealerDouble')
def dDraw():
    mutex.acquire()
    global dealerCardTotal
    try:
        dealerHand = Hands.query.filter_by(user_id=1).first()
        testing = Cards.query.filter_by(hand_id=dealerHand.id).all()
        if len(testing) == 0:
            print("requesting card")
            cardList = []
            for i in range(2):
                deck = Cards.query.filter_by(dealt=0).all()
                if len(deck) > 0:
                    card = random.choice(deck)
                    card.dealt = 1
                    card.hand_id = dealerHand.id
                    db.session.commit()
                    rank = card.crank
                    if rank == 'jack':
                        rank = 10
                    elif rank == 'queen':
                        rank = 10
                    elif rank == 'king':
                        rank = 10
                    elif rank == 'ace':
                        if dealerCardTotal >= 11:
                            rank = 1
                        elif dealerCardTotal < 11:
                            rank = 11
                    dealerCardTotal += int(rank)
                    print("Total: " + str(dealerCardTotal))
                else:
                    print("need to reshuffle")
                cardList.append({'image': card.imageSrc})

            newDeal = json.dumps(cardList)
            socketio.emit('dealerDisplay', data=(newDeal,dealerCardTotal))
    finally:
        mutex.release()



def dealerHit():
    global dealerCardTotal
    dealerHand = Hands.query.filter_by(user_id=1).first()
    deck = Cards.query.filter_by(dealt=0).all()
    if len(deck) > 0:
        card = random.choice(deck)
        card.dealt = 1
        card.hand_id = dealerHand.id
        db.session.commit()
        rank = card.crank
        if rank == 'jack':
            rank = 10
        elif rank == 'queen':
            rank = 10
        elif rank == 'king':
            rank = 10
        elif rank == 'ace':
            if dealerCardTotal >= 11:
                rank = 1
            elif dealerCardTotal < 11:
                rank = 11
        dealerCardTotal += int(rank)
        print("Total: " + str(dealerCardTotal))
    else:
        shuffle()
        print("need to reshuffle")

    dHit = {'image': card.imageSrc}
    print(json.dumps(dHit))
    newDHit = json.dumps(dHit)
    socketio.emit('dealerDisplaySingle', data=(newDHit,dealerCardTotal))
    dealerLog()


def dealerLog():
    total = 0
    dealCheck = True
    dealerHand = Hands.query.filter_by(user_id=1).first()
    dealersCards = Cards.query.filter_by(hand_id=dealerHand.id).all()
    for d in dealersCards:
        if d.crank == "jack" or d.crank == "queen" or d.crank == "king":
            total += 10
        elif d.crank == "ace":
            if total >= 11:
                total += 1
            else:
                total += 11
        else:
            total += int(d.crank)

    if total <= 17:
        dealerHit()
        dealCheck = False
    else:
        if total < 21 and dealCheck == False:
            dealerHit()
        else:
            endgame()


@socketio.on('splitLogic')
def splitLog():
    global users,cardTotal
    cardList = []
    currPlayer = users[count]
    users.insert(count+1, currPlayer)

    playerHand = Hands.query.filter_by(user_id=current_user.id).all()
    hand = Hands.query.filter_by(user_id=current_user.id).first()
    playersCards = Cards.query.filter_by(hand_id=hand.id).all()

    playersCards[0].hand_id = playerHand[0].id
    playersCards[1].hand_id = playerHand[1].id
    db.session.commit()
    for card in playersCards:
        rank = card.crank
        if rank == 'jack':
            rank = 10
        elif rank == 'queen':
            rank = 10
        elif rank == 'king':
            rank = 10
        elif rank == 'ace':
            if cardTotal >= 11:
                rank = 1
            elif cardTotal < 11:
                rank = 11
            cardTotal += int(rank)
        print("Total: " + str(cardTotal))

    cardList.append({'image': playersCards[0].imageSrc})
    cardList.append({'image': playersCards[1].imageSrc})
    newDeal = json.dumps(cardList)
    name = str(current_user.username)

    socketio.emit('splitDisplay', data=(newDeal, str(current_user), name,cardTotal))


####App Routes and Template Rendering####
@app.route("/", methods=['POST', 'GET'])
def index():
    return redirect('/login')

@app.route('/gameOver')
def endgame():
    print("Game Over")
    socketio.emit('gameOver')

@app.route('/playAgain')
def playAgain():
    global cardTotal
    cardTotal = 0
    return redirect('/dealer')

@app.route("/burst")
def burst():
    userCash = User.query.filter_by(id=current_user.id).first()
    userCash.money = userCash.money - userCash.bets
    db.session.commit()
    socketio.emit('burst')

@app.route('/login', methods=['POST', 'GET'])
def login():
    error = False
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user is not None and user.password == password:
            login_user(user)
            return redirect('/dealer')
        if user is None or user.password != password:
            error = True
            return render_template('blackJackLogin.html', error=error)
    return render_template('blackJackLogin.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    socketio.emit('disconnect')
    return redirect('/login')

@app.route('/dealer', methods=['POST', 'GET'])
@login_required
def deal():
    userCash = User.query.filter_by(id=current_user.id).first()
    userCash.bets = 0
    return render_template('dealer.html')

def shuffle():
    deck = Cards.query.filter_by(dealt=1).all()
    for card in deck:
        card.dealt = 0
        card.hand_id = 0
    db.session.commit()
    return redirect('/dealer')

####Main Function####
if __name__ == '__main__':
    socketio.run(app, allow_unsafe_werkzeug=True)
