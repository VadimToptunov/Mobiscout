"""
Mock Backend API for FinDemo App - Revolut/Wise Clone

Complete fintech API with multi-currency accounts, exchange, cards, and more.
STEP 7: Paid Modules Enhancement - Mock Backend Security Refactoring
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Security Configuration
DEFAULT_TEST_PASSWORD = os.getenv("TEST_PASSWORD", "password")


def hash_password(password: str) -> str:
    """
    Hash password using SHA-256 for demo purposes.

    WARNING: In production, use proper password hashing like bcrypt or argon2.
    This is intentionally simple for testing purposes only.

    Args:
        password: Plain text password to hash

    Returns:
        Hexadecimal SHA-256 hash of the password
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.

    Args:
        plain_password: Plain text password to check
        hashed_password: Stored hash to compare against

    Returns:
        True if password matches, False otherwise
    """
    return hash_password(plain_password) == hashed_password


app = FastAPI(
    title="FinDemo API - Fintech Platform",
    description="Complete fintech API (Revolut/Wise clone) for Mobile Test Framework",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Models ====================

# Auth Models
class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None


class AuthResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user_id: Optional[str] = None
    message: str


# User Models
class UserProfile(BaseModel):
    user_id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    kyc_status: str
    created_at: str
    photo_url: Optional[str] = None


# Account Models
class CurrencyAccount(BaseModel):
    currency: str
    balance: float
    account_number: Optional[str] = None


class MultiCurrencyBalance(BaseModel):
    accounts: List[CurrencyAccount]
    primary_currency: str
    total_in_primary: float


# Card Models
class Card(BaseModel):
    card_id: str
    card_number: str  # Masked: **** 1234
    card_type: str  # physical, virtual
    status: str  # active, blocked, expired
    currency: str
    balance: float
    expiry_date: str
    cvv: str
    cardholder_name: str


# Transaction Models
class Transaction(BaseModel):
    id: str
    type: str  # send, receive, topup, exchange, card_payment, atm_withdrawal
    amount: float
    currency: str
    from_currency: Optional[str] = None
    to_currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    recipient: Optional[str] = None
    sender: Optional[str] = None
    merchant: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    timestamp: str
    status: str
    fee: float = 0.0


# Exchange Models
class ExchangeRate(BaseModel):
    from_currency: str
    to_currency: str
    rate: float
    inverse_rate: float
    timestamp: str


class ExchangeRequest(BaseModel):
    from_currency: str
    to_currency: str
    amount: float


# Payment Models
class TopUpRequest(BaseModel):
    amount: float
    currency: str = "USD"
    payment_method: str  # card, bank_transfer


class SendMoneyRequest(BaseModel):
    recipient_id: str
    amount: float
    currency: str
    note: Optional[str] = None


class RequestMoneyModel(BaseModel):
    from_user_id: str
    amount: float
    currency: str
    note: Optional[str] = None


# Contact Models
class Contact(BaseModel):
    contact_id: str
    user_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    is_favorite: bool = False


# KYC Models
class KYCDocument(BaseModel):
    document_type: str
    document_number: str
    full_name: str
    date_of_birth: str
    nationality: str


# ==================== Mock Data ====================

# Exchange rates
exchange_rates = {
    "USD": {"EUR": 0.92, "GBP": 0.79, "JPY": 149.50, "CHF": 0.88},
    "EUR": {"USD": 1.09, "GBP": 0.86, "JPY": 162.50, "CHF": 0.96},
    "GBP": {"USD": 1.27, "EUR": 1.16, "JPY": 189.30, "CHF": 1.11},
}

# Users database
# ⚠️ WARNING: Passwords in plain text - FOR DEMO ONLY
users_db = {
    "user123": {
        "user_id": "user123",
        "email": "john@example.com",
        "full_name": "John Doe",
        "phone": "+1234567890",
        "password": hash_password(DEFAULT_TEST_PASSWORD),  # Configurable via env
        "kyc_status": "verified",
        "created_at": "2024-01-15T10:00:00Z",
        "photo_url": None,
        "accounts": {
            "USD": {"balance": 1250.50, "account_number": "US12345678"},
            "EUR": {"balance": 850.25, "account_number": "EU87654321"},
            "GBP": {"balance": 420.00, "account_number": "GB11223344"},
        },
        "primary_currency": "USD"
    }
}

# Cards database
cards_db = {
    "card001": {
        "card_id": "card001",
        "user_id": "user123",
        "card_number": "**** **** **** 1234",
        "full_number": "4532123456781234",  # For demo
        "card_type": "physical",
        "status": "active",
        "currency": "USD",
        "balance": 500.00,
        "expiry_date": "12/27",
        "cvv": "123",
        "cardholder_name": "JOHN DOE"
    },
    "card002": {
        "card_id": "card002",
        "user_id": "user123",
        "card_number": "**** **** **** 5678",
        "full_number": "4532876543215678",
        "card_type": "virtual",
        "status": "active",
        "currency": "EUR",
        "balance": 300.00,
        "expiry_date": "09/26",
        "cvv": "456",
        "cardholder_name": "JOHN DOE"
    }
}

# Contacts database
contacts_db = {
    "contact001": {
        "contact_id": "contact001",
        "user_id": "user123",
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "phone": "+1234567891",
        "photo_url": None,
        "is_favorite": True
    },
    "contact002": {
        "contact_id": "contact002",
        "user_id": "user123",
        "name": "Bob Smith",
        "email": "bob@example.com",
        "phone": "+1234567892",
        "photo_url": None,
        "is_favorite": False
    },
    "contact003": {
        "contact_id": "contact003",
        "user_id": "user123",
        "name": "Carol White",
        "email": "carol@example.com",
        "phone": "+1234567893",
        "photo_url": None,
        "is_favorite": True
    }
}

# Transactions database
transactions_db = []


def create_transaction(user_id: str, **kwargs) -> Dict:
    """Helper to create transaction"""
    tx = {
        "id": f"tx{uuid.uuid4().hex[:8]}",
        "user_id": user_id,
        "timestamp": datetime.now().isoformat() + "Z",
        "status": "completed",
        "fee": 0.0,
        **kwargs
    }
    transactions_db.insert(0, tx)
    return tx


# Initialize with some mock transactions
create_transaction("user123", type="receive", amount=100.00, currency="USD", sender="Alice Johnson", category="p2p")
create_transaction("user123", type="send", amount=50.00, currency="USD", recipient="Bob Smith", note="Dinner",
                   category="p2p")
create_transaction("user123", type="topup", amount=200.00, currency="USD", category="topup")
create_transaction("user123", type="card_payment", amount=45.99, currency="USD", merchant="Amazon", category="shopping")
create_transaction("user123", type="card_payment", amount=12.50, currency="EUR", merchant="Starbucks", category="food")


# ==================== Helper Functions ====================

def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify auth token (mock - always returns user123)"""
    if not authorization:
        return "user123"  # For demo - no auth required
    return "user123"


def get_exchange_rate(from_curr: str, to_curr: str) -> float:
    """Get exchange rate between currencies"""
    if from_curr == to_curr:
        return 1.0
    if from_curr in exchange_rates and to_curr in exchange_rates[from_curr]:
        return exchange_rates[from_curr][to_curr]
    # Inverse rate
    if to_curr in exchange_rates and from_curr in exchange_rates[to_curr]:
        return 1.0 / exchange_rates[to_curr][from_curr]
    return 1.0  # Default


# ==================== Routes ====================

@app.get("/")
def root():
    """API health check"""
    return {
        "service": "FinDemo API - Fintech Platform",
        "status": "healthy",
        "version": "1.0.0",
        "features": [
            "Multi-currency accounts",
            "Currency exchange",
            "Virtual & Physical cards",
            "P2P payments",
            "International transfers",
            "Transaction history"
        ]
    }


# ==================== Auth ====================

@app.post("/api/auth/login", response_model=AuthResponse)
def login(request: LoginRequest):
    """
    User login endpoint with secure password verification.

    Args:
        request: Login credentials containing email and password

    Returns:
        AuthResponse with token and user information

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Find user by email
    user = next((u for u in users_db.values() if u["email"] == request.email), None)

    if not user or not verify_password(request.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthResponse(
        success=True,
        token=f"token_{uuid.uuid4().hex[:16]}",
        user_id=user["user_id"],
        message="Login successful"
    )


@app.post("/api/auth/register", response_model=AuthResponse)
def register(request: RegisterRequest):
    """
    Register new user with hashed password storage.

    Args:
        request: Registration details including email, password, and profile info

    Returns:
        AuthResponse with token and new user ID

    Raises:
        HTTPException: 400 if email is already registered
    """
    # Check if email exists
    if any(u["email"] == request.email for u in users_db.values()):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = f"user{uuid.uuid4().hex[:8]}"
    users_db[user_id] = {
        "user_id": user_id,
        "email": request.email,
        "full_name": request.full_name,
        "phone": request.phone,
        "password": hash_password(request.password),
        "kyc_status": "pending",
        "created_at": datetime.now().isoformat() + "Z",
        "photo_url": None,
        "accounts": {
            "USD": {"balance": 0.0, "account_number": f"US{uuid.uuid4().hex[:8]}"},
        },
        "primary_currency": "USD"
    }

    return AuthResponse(
        success=True,
        token=f"token_{uuid.uuid4().hex[:16]}",
        user_id=user_id,
        message="Registration successful"
    )


# ==================== User Profile ====================

@app.get("/api/user/profile", response_model=UserProfile)
def get_profile(authorization: Optional[str] = Header(None)):
    """Get user profile"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]
    return UserProfile(
        user_id=user["user_id"],
        email=user["email"],
        full_name=user["full_name"],
        phone=user.get("phone"),
        kyc_status=user["kyc_status"],
        created_at=user["created_at"],
        photo_url=user.get("photo_url")
    )


@app.put("/api/user/profile")
def update_profile(full_name: Optional[str] = None, phone: Optional[str] = None,
                   authorization: Optional[str] = Header(None)):
    """Update user profile"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    if full_name:
        users_db[user_id]["full_name"] = full_name
    if phone:
        users_db[user_id]["phone"] = phone

    return {"success": True, "message": "Profile updated"}


# ==================== Accounts & Balance ====================

@app.get("/api/accounts", response_model=MultiCurrencyBalance)
def get_accounts(authorization: Optional[str] = Header(None)):
    """Get all currency accounts"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]
    accounts = []

    for currency, account in user["accounts"].items():
        accounts.append(CurrencyAccount(
            currency=currency,
            balance=account["balance"],
            account_number=account.get("account_number")
        ))

    # Calculate total in primary currency
    primary = user["primary_currency"]
    total = sum(
        acc["balance"] if curr == primary else acc["balance"] * get_exchange_rate(curr, primary)
        for curr, acc in user["accounts"].items()
    )

    return MultiCurrencyBalance(
        accounts=accounts,
        primary_currency=primary,
        total_in_primary=round(float(total), 2)
    )


@app.post("/api/accounts/add")
def add_currency_account(currency: str, authorization: Optional[str] = Header(None)):
    """Add new currency account"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    if currency in users_db[user_id]["accounts"]:
        raise HTTPException(status_code=400, detail="Account already exists")

    users_db[user_id]["accounts"][currency] = {
        "balance": 0.0,
        "account_number": f"{currency[:2]}{uuid.uuid4().hex[:8]}"
    }

    return {"success": True, "message": f"{currency} account created"}


# ==================== Currency Exchange ====================

@app.get("/api/exchange/rates")
def get_rates(base_currency: str = "USD"):
    """Get exchange rates"""
    rates = []

    for from_curr in ["USD", "EUR", "GBP", "JPY", "CHF"]:
        for to_curr in ["USD", "EUR", "GBP", "JPY", "CHF"]:
            if from_curr != to_curr:
                rate = get_exchange_rate(from_curr, to_curr)
                rates.append(ExchangeRate(
                    from_currency=from_curr,
                    to_currency=to_curr,
                    rate=rate,
                    inverse_rate=1 / rate if rate > 0 else 0,
                    timestamp=datetime.now().isoformat() + "Z"
                ))

    return rates


@app.post("/api/exchange")
def exchange_currency(request: ExchangeRequest, authorization: Optional[str] = Header(None)):
    """Exchange currency"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    user = users_db[user_id]

    # Check balance
    if request.from_currency not in user["accounts"]:
        raise HTTPException(status_code=400, detail=f"No {request.from_currency} account")

    if user["accounts"][request.from_currency]["balance"] < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Get exchange rate
    rate = get_exchange_rate(request.from_currency, request.to_currency)
    exchanged_amount = round(request.amount * rate, 2)

    # Add to_currency account if doesn't exist
    if request.to_currency not in user["accounts"]:
        user["accounts"][request.to_currency] = {
            "balance": 0.0,
            "account_number": f"{request.to_currency[:2]}{uuid.uuid4().hex[:8]}"
        }

    # Update balances
    user["accounts"][request.from_currency]["balance"] -= request.amount
    user["accounts"][request.to_currency]["balance"] += exchanged_amount

    # Create transaction
    tx = create_transaction(
        user_id,
        type="exchange",
        amount=request.amount,
        currency=request.from_currency,
        from_currency=request.from_currency,
        to_currency=request.to_currency,
        exchange_rate=rate,
        category="exchange",
        note=f"Exchanged to {exchanged_amount} {request.to_currency}"
    )

    return {
        "success": True,
        "transaction_id": tx["id"],
        "exchanged_amount": exchanged_amount,
        "rate": rate,
        "message": f"Exchanged {request.amount} {request.from_currency} to {exchanged_amount} {request.to_currency}"
    }


# ==================== Cards ====================

@app.get("/api/cards", response_model=List[Card])
def get_cards(authorization: Optional[str] = Header(None)):
    """Get user's cards"""
    user_id = verify_token(authorization)

    user_cards = [card for card in cards_db.values() if card["user_id"] == user_id]

    return [Card(**card) for card in user_cards]


@app.post("/api/cards/create")
def create_card(card_type: str, currency: str = "USD", authorization: Optional[str] = Header(None)):
    """Create new virtual card"""
    user_id = verify_token(authorization)

    if card_type not in ["virtual", "physical"]:
        raise HTTPException(status_code=400, detail="Invalid card type")

    card_id = f"card{uuid.uuid4().hex[:6]}"
    card_number = f"4532{uuid.uuid4().hex[:12]}"

    card = {
        "card_id": card_id,
        "user_id": user_id,
        "card_number": f"**** **** **** {card_number[-4:]}",
        "full_number": card_number,
        "card_type": card_type,
        "status": "active",
        "currency": currency,
        "balance": 0.0,
        "expiry_date": f"{(datetime.now() + timedelta(days=1095)).strftime('%m/%y')}",
        "cvv": str(uuid.uuid4().int % 1000).zfill(3),
        "cardholder_name": users_db[user_id]["full_name"].upper()
    }

    cards_db[card_id] = card

    return {"success": True, "card": Card(**card)}


@app.post("/api/cards/{card_id}/block")
def block_card(card_id: str, authorization: Optional[str] = Header(None)):
    """Block/unblock card"""
    user_id = verify_token(authorization)

    if card_id not in cards_db or cards_db[card_id]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Card not found")

    current_status = cards_db[card_id]["status"]
    new_status = "blocked" if current_status == "active" else "active"
    cards_db[card_id]["status"] = new_status

    return {"success": True, "status": new_status}


# ==================== Transactions ====================

@app.get("/api/transactions", response_model=List[Transaction])
def get_transactions(limit: int = 20, category: Optional[str] = None,
                     authorization: Optional[str] = Header(None)):
    """Get transaction history"""
    user_id = verify_token(authorization)

    user_txs = [tx for tx in transactions_db if tx.get("user_id") == user_id]

    if category:
        user_txs = [tx for tx in user_txs if tx.get("category") == category]

    return [Transaction(**tx) for tx in user_txs[:limit]]


# ==================== Payments ====================

@app.post("/api/topup")
def topup(request: TopUpRequest, authorization: Optional[str] = Header(None)):
    """Add funds to account"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Add to account
    if request.currency not in users_db[user_id]["accounts"]:
        raise HTTPException(status_code=400, detail=f"No {request.currency} account")

    users_db[user_id]["accounts"][request.currency]["balance"] += request.amount

    tx = create_transaction(
        user_id,
        type="topup",
        amount=request.amount,
        currency=request.currency,
        category="topup"
    )

    return {
        "success": True,
        "transaction_id": tx["id"],
        "new_balance": users_db[user_id]["accounts"][request.currency]["balance"]
    }


@app.post("/api/send")
def send_money(request: SendMoneyRequest, authorization: Optional[str] = Header(None)):
    """Send money to contact"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Check balance
    if request.currency not in users_db[user_id]["accounts"]:
        raise HTTPException(status_code=400, detail=f"No {request.currency} account")

    if users_db[user_id]["accounts"][request.currency]["balance"] < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Deduct from sender
    users_db[user_id]["accounts"][request.currency]["balance"] -= request.amount

    # Get recipient name
    contact = contacts_db.get(request.recipient_id, {})
    recipient_name = contact.get("name", "Unknown")

    tx = create_transaction(
        user_id,
        type="send",
        amount=request.amount,
        currency=request.currency,
        recipient=recipient_name,
        note=request.note,
        category="p2p"
    )

    return {
        "success": True,
        "transaction_id": tx["id"],
        "new_balance": users_db[user_id]["accounts"][request.currency]["balance"]
    }


# ==================== Contacts ====================

@app.get("/api/contacts", response_model=List[Contact])
def get_contacts(authorization: Optional[str] = Header(None)):
    """Get user contacts"""
    user_id = verify_token(authorization)

    user_contacts = [c for c in contacts_db.values() if c["user_id"] == user_id]
    return [Contact(**c) for c in user_contacts]


@app.post("/api/contacts/add")
def add_contact(name: str, email: Optional[str] = None, phone: Optional[str] = None,
                authorization: Optional[str] = Header(None)):
    """Add new contact"""
    user_id = verify_token(authorization)

    contact_id = f"contact{uuid.uuid4().hex[:6]}"
    contact = {
        "contact_id": contact_id,
        "user_id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "photo_url": None,
        "is_favorite": False
    }

    contacts_db[contact_id] = contact
    return {"success": True, "contact": Contact(**contact)}


# ==================== KYC ====================

@app.post("/api/kyc/verify")
def verify_kyc(request: KYCDocument, authorization: Optional[str] = Header(None)):
    """Submit KYC verification"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Mock: always approve
    users_db[user_id]["kyc_status"] = "verified"

    return {
        "success": True,
        "verification_id": f"kyc_{uuid.uuid4().hex[:8]}",
        "status": "verified",
        "message": "KYC verification successful"
    }


@app.get("/api/kyc/status")
def get_kyc_status(authorization: Optional[str] = Header(None)):
    """Get KYC status"""
    user_id = verify_token(authorization)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_id,
        "kyc_status": users_db[user_id]["kyc_status"],
        "verified_at": datetime.now().isoformat() + "Z"
    }


# ==================== Main ====================

if __name__ == "__main__":
    print(" Starting FinDemo API - Fintech Platform")
    print("=" * 60)
    print(" Server: http://localhost:8000")
    print(" Docs: http://localhost:8000/docs")
    print(" ReDoc: http://localhost:8000/redoc")
    print("=" * 60)
    print(" Features:")
    print("   • Multi-currency accounts (USD, EUR, GBP, JPY, CHF)")
    print("   • Real-time currency exchange")
    print("   • Virtual & Physical cards")
    print("   • P2P payments")
    print("   • Transaction history")
    print("   • Contact management")
    print("   • KYC verification")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
