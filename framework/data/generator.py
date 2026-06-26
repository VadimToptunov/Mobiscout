"""
Test Data Generator

Generate realistic test data for mobile applications.
"""

import json
import os
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional


class DataType(Enum):
    """Types of test data"""
    USER = "user"
    PRODUCT = "product"
    TRANSACTION = "transaction"
    CARD = "card"
    ADDRESS = "address"


@dataclass
class User:
    """User test data"""
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    date_of_birth: str
    password: str = "Test123!"
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Product:
    """Product test data"""
    id: str
    name: str
    description: str
    price: float
    currency: str = "USD"
    category: str = "general"
    stock: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transaction:
    """Transaction test data"""
    id: str
    user_id: str
    amount: float
    currency: str = "USD"
    type: str = "payment"
    status: str = "completed"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CreditCard:
    """Credit card test data"""
    number: str
    cvv: str
    expiry_month: str
    expiry_year: str
    holder_name: str
    type: str = "visa"


@dataclass
class Address:
    """Address test data"""
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


class TestDataGenerator:
    """Generate realistic test data"""

    # Sample data pools
    FIRST_NAMES = [
        "John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa",
        "James", "Mary", "William", "Patricia", "Richard", "Jennifer", "Thomas"
    ]

    LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez"
    ]

    CITIES = [
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
        "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville"
    ]

    STATES = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "GA", "NC"]

    STREETS = [
        "Main Street", "Oak Avenue", "Park Road", "Maple Drive", "Cedar Lane",
        "Pine Street", "Elm Avenue", "Washington Boulevard", "Lincoln Way"
    ]

    PRODUCT_NAMES = [
        "Premium Widget", "Deluxe Gadget", "Professional Tool", "Standard Kit",
        "Advanced System", "Basic Package", "Elite Set", "Ultimate Bundle"
    ]

    PRODUCT_CATEGORIES = [
        "electronics", "clothing", "home", "sports", "books", "toys", "food", "beauty"
    ]

    def __init__(self, seed: Optional[int] = None):
        """Initialize generator with optional seed for reproducibility"""
        if seed:
            random.seed(seed)

    def _generate_secure_password(self) -> str:
        """Generate a secure test password"""
        # Use environment variable for consistent test passwords, or generate secure random
        test_password = os.environ.get('TEST_USER_PASSWORD')
        if test_password:
            return test_password

        # Generate secure random password for test data
        chars = string.ascii_letters + string.digits + "!@#$%"
        password = ''.join(random.choice(chars) for _ in range(12))
        # Ensure it meets basic requirements
        if not any(c.isupper() for c in password):
            password = password[0].upper() + password[1:]
        if not any(c.isdigit() for c in password):
            password = password[:-1] + str(random.randint(0, 9))
        return password

    def generate_users(self, count: int) -> List[User]:
        """Generate user test data"""
        users = []
        for i in range(count):
            first_name = random.choice(self.FIRST_NAMES)
            last_name = random.choice(self.LAST_NAMES)

            user = User(
                id=self._generate_id("user"),
                first_name=first_name,
                last_name=last_name,
                email=self._generate_email(first_name, last_name),
                phone=self._generate_phone(),
                date_of_birth=self._generate_dob(),
                password=self._generate_secure_password(),
                status=random.choice(["active", "pending", "suspended"]),
                metadata={"created_at": datetime.now().isoformat()}
            )
            users.append(user)

        return users

    def generate_products(self, count: int) -> List[Product]:
        """Generate product test data"""
        products = []
        for i in range(count):
            name = random.choice(self.PRODUCT_NAMES)
            category = random.choice(self.PRODUCT_CATEGORIES)

            product = Product(
                id=self._generate_id("prod"),
                name=f"{name} {i + 1}",
                description=f"High quality {category} product",
                price=round(random.uniform(9.99, 999.99), 2),
                currency="USD",
                category=category,
                stock=random.randint(0, 1000),
                metadata={"sku": self._generate_id("SKU")}
            )
            products.append(product)

        return products

    def generate_transactions(self, count: int, user_ids: Optional[List[str]] = None) -> List[Transaction]:
        """Generate transaction test data"""
        transactions = []

        if not user_ids:
            user_ids = [self._generate_id("user") for _ in range(10)]

        for i in range(count):
            transaction = Transaction(
                id=self._generate_id("txn"),
                user_id=random.choice(user_ids),
                amount=round(random.uniform(1.00, 10000.00), 2),
                currency="USD",
                type=random.choice(["payment", "refund", "transfer"]),
                status=random.choice(["completed", "pending", "failed"]),
                timestamp=self._generate_timestamp(),
                metadata={"reference": self._generate_id("ref")}
            )
            transactions.append(transaction)

        return transactions

    def generate_cards(self, count: int) -> List[CreditCard]:
        """Generate credit card test data"""
        cards = []
        for i in range(count):
            card_type = random.choice(["visa", "mastercard", "amex"])

            card = CreditCard(
                number=self._generate_card_number(card_type),
                cvv=self._generate_cvv(card_type),
                expiry_month=f"{random.randint(1, 12):02d}",
                expiry_year=str(random.randint(2025, 2030)),
                holder_name=f"{random.choice(self.FIRST_NAMES)} {random.choice(self.LAST_NAMES)}".upper(),
                type=card_type
            )
            cards.append(card)

        return cards

    def generate_addresses(self, count: int) -> List[Address]:
        """Generate address test data"""
        addresses = []
        for i in range(count):
            address = Address(
                street=f"{random.randint(100, 9999)} {random.choice(self.STREETS)}",
                city=random.choice(self.CITIES),
                state=random.choice(self.STATES),
                zip_code=f"{random.randint(10000, 99999)}",
                country="US"
            )
            addresses.append(address)

        return addresses

    def _generate_id(self, prefix: str = "") -> str:
        """Generate random ID"""
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        return f"{prefix}_{suffix}" if prefix else suffix

    def _generate_email(self, first_name: str, last_name: str) -> str:
        """Generate email address"""
        domains = ["example.com", "test.com", "demo.com", "sample.com"]
        return f"{first_name.lower()}.{last_name.lower()}@{random.choice(domains)}"

    def _generate_phone(self) -> str:
        """Generate US phone number"""
        area = random.randint(200, 999)
        prefix = random.randint(200, 999)
        line = random.randint(1000, 9999)
        return f"+1-{area}-{prefix}-{line}"

    def _generate_dob(self) -> str:
        """Generate date of birth (18-80 years old)"""
        today = datetime.now()
        years_ago = random.randint(18, 80)
        dob = today - timedelta(days=years_ago * 365)
        return dob.strftime("%Y-%m-%d")

    def _generate_timestamp(self) -> str:
        """Generate recent timestamp"""
        days_ago = random.randint(0, 30)
        timestamp = datetime.now() - timedelta(days=days_ago)
        return timestamp.isoformat()

    def _generate_card_number(self, card_type: str) -> str:
        """Generate test credit card number"""
        if card_type == "visa":
            return f"4{random.randint(100000000000000, 999999999999999)}"
        elif card_type == "mastercard":
            return f"5{random.randint(100000000000000, 999999999999999)}"
        else:  # amex
            return f"3{random.randint(10000000000000, 99999999999999)}"

    def _generate_cvv(self, card_type: str) -> str:
        """Generate CVV"""
        if card_type == "amex":
            return f"{random.randint(1000, 9999)}"
        else:
            return f"{random.randint(100, 999)}"

    def export_json(self, data: List[Any], output_path: str) -> None:
        """Export data to JSON file"""
        with open(output_path, 'w') as f:
            json_data = [self._to_dict(item) for item in data]
            json.dump(json_data, f, indent=2)

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert dataclass to dict"""
        if hasattr(obj, '__dataclass_fields__'):
            return {k: v for k, v in obj.__dict__.items()}
        return obj
