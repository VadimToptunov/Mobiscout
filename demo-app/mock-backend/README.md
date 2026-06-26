# FinDemo API - Fintech Platform

Complete **Revolut/Wise clone** mock backend with multi-currency, exchange, cards, and P2P payments.

---

## Features

### Multi-Currency Accounts

- Support for **5 major currencies**: USD, EUR, GBP, JPY, CHF
- Real-time balance tracking per currency
- Automatic account creation
- Primary currency setting

### Currency Exchange

- Real-time exchange rates
- Instant currency conversion
- Low fees (0% for demo)
- Exchange history tracking

### Cards

- **Virtual cards** - Instant creation
- **Physical cards** - For ATM/POS
- Per-card spending limits
- Block/unblock functionality
- Multiple currencies per card

### P2P Payments

- Send money to contacts
- Request money from users
- Split bills
- Add notes to transactions

### Transaction History

- Detailed transaction log
- Filter by category (P2P, shopping, food, etc.)
- Real-time updates
- Export functionality

### Contacts Management

- Add/remove contacts
- Favorite contacts
- Quick send to favorites

### KYC Verification

- Document upload simulation
- Identity verification
- Status tracking

---

## API Endpoints

### Authentication

```http
POST /api/auth/login
POST /api/auth/register
```

### User Profile

```http
GET  /api/user/profile
PUT  /api/user/profile
```

### Accounts & Balance

```http
GET  /api/accounts              # Get all currency accounts
POST /api/accounts/add          # Add new currency
```

### Currency Exchange

```http
GET  /api/exchange/rates        # Get exchange rates
POST /api/exchange              # Exchange currency
```

### Cards

```http
GET  /api/cards                 # Get all cards
POST /api/cards/create          # Create virtual card
POST /api/cards/{id}/block      # Block/unblock card
```

### Transactions

```http
GET  /api/transactions          # Get history
```

### Payments

```http
POST /api/topup                 # Add funds
POST /api/send                  # Send money
```

### Contacts

```http
GET  /api/contacts              # Get contacts
POST /api/contacts/add          # Add contact
```

### KYC

```http
POST /api/kyc/verify            # Submit KYC
GET  /api/kyc/status            # Check status
```

---

## Setup & Run

### Requirements

```bash
pip install fastapi uvicorn pydantic
```

### Start Server

```bash
cd demo-app/mock-backend
python main.py
```

Server will start on `http://localhost:8000`

### Access Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Example Requests

### Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "password"
  }'
```

### Get Multi-Currency Balance

```bash
curl http://localhost:8000/api/accounts
```

**Response:**

```json
{
  "accounts": [
    {
      "currency": "USD",
      "balance": 1250.50,
      "account_number": "US12345678"
    },
    {
      "currency": "EUR",
      "balance": 850.25,
      "account_number": "EU87654321"
    },
    {
      "currency": "GBP",
      "balance": 420.00,
      "account_number": "GB11223344"
    }
  ],
  "primary_currency": "USD",
  "total_in_primary": 2850.75
}
```

### Exchange Currency

```bash
curl -X POST http://localhost:8000/api/exchange \
  -H "Content-Type: application/json" \
  -d '{
    "from_currency": "USD",
    "to_currency": "EUR",
    "amount": 100.00
  }'
```

**Response:**

```json
{
  "success": true,
  "transaction_id": "tx12345678",
  "exchanged_amount": 92.00,
  "rate": 0.92,
  "message": "Exchanged 100.0 USD to 92.0 EUR"
}
```

### Create Virtual Card

```bash
curl -X POST http://localhost:8000/api/cards/create \
  -H "Content-Type: application/json" \
  -d '{
    "card_type": "virtual",
    "currency": "EUR"
  }'
```

### Get Transaction History

```bash
curl http://localhost:8000/api/transactions?limit=10&category=p2p
```

### Send Money

```bash
curl -X POST http://localhost:8000/api/send \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_id": "contact001",
    "amount": 50.00,
    "currency": "USD",
    "note": "Dinner split"
  }'
```

---

## Mock Data

### Default User

```json
{
  "email": "john@example.com",
  "password": "password",
  "user_id": "user123"
}
```

### Default Accounts

- **USD**: $1,250.50
- **EUR**: €850.25
- **GBP**: £420.00

### Default Cards

- Physical Card: `**** 1234` (USD)
- Virtual Card: `**** 5678` (EUR)

### Default Contacts

- Alice Johnson
- Bob Smith
- Carol White

### Exchange Rates (Mock)

| From | To  | Rate |
|------|-----|------|
| USD  | EUR | 0.92 |
| USD  | GBP | 0.79 |
| EUR  | USD | 1.09 |
| GBP  | USD | 1.27 |

---

## Transaction Categories

- `p2p` - Person to person
- `topup` - Account funding
- `exchange` - Currency exchange
- `card_payment` - Card purchase
- `atm_withdrawal` - ATM cash
- `shopping` - Online shopping
- `food` - Restaurants
- `transport` - Travel
- `entertainment` - Fun

---

## Authentication

**For demo purposes**, authentication is **optional**.

All endpoints work without tokens and default to `user123`.

To use auth:

1. Login to get token
2. Pass `Authorization: Bearer <token>` header

---

## Mobile App Integration

### Android (Retrofit)

```kotlin
interface FinDemoApi {
    @GET("api/accounts")
    suspend fun getAccounts(): MultiCurrencyBalance
    
    @POST("api/exchange")
    suspend fun exchange(@Body request: ExchangeRequest): ExchangeResponse
    
    @GET("api/cards")
    suspend fun getCards(): List<Card>
}
```

### iOS (URLSession)

```swift
struct FinDemoAPI {
    let baseURL = "http://localhost:8000"
    
    func getAccounts() async throws -> MultiCurrencyBalance {
        let url = URL(string: "\(baseURL)/api/accounts")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(MultiCurrencyBalance.self, from: data)
    }
}
```

---

## 🧪 Testing

### Health Check

```bash
curl http://localhost:8000/
```

### Test Complete Flow

```bash
# 1. Login
curl -X POST http://localhost:8000/api/auth/login \
  -d '{"email":"john@example.com","password":"password"}'

# 2. Get balance
curl http://localhost:8000/api/accounts

# 3. Exchange 100 USD to EUR
curl -X POST http://localhost:8000/api/exchange \
  -d '{"from_currency":"USD","to_currency":"EUR","amount":100}'

# 4. Create virtual card
curl -X POST http://localhost:8000/api/cards/create \
  -d '{"card_type":"virtual","currency":"EUR"}'

# 5. Send money to contact
curl -X POST http://localhost:8000/api/send \
  -d '{"recipient_id":"contact001","amount":50,"currency":"USD","note":"Thanks!"}'
```

---

## Next Steps

1. **Connect Mobile Apps**: Update Android/iOS apps to use new endpoints
2. **Add Real Data**: Replace mock data with database
3. **Implement Auth**: Add JWT authentication
4. **Add WebSockets**: Real-time balance updates
5. **Add Notifications**: Push notifications for transactions
6. **Add Analytics**: Track user behavior

---

## API Documentation

Full interactive documentation available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

**Built for Mobile Observe & Test Framework**   
**Simulating Revolut/Wise experience** 
