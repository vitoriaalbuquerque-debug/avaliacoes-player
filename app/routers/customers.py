from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, RestaurantTable
from app.schemas import CustomerLookupRequest, CustomerLookupResponse
from app.services.security import hash_cpf, is_valid_cpf_format

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/lookup", response_model=CustomerLookupResponse)
def lookup_customer(payload: CustomerLookupRequest, db: Session = Depends(get_db)):
    """
    Primeira tela do fluxo do cliente: confirma o CPF, conecta (ou cria) o
    registro do cliente, e resolve a mesa pra sessão atual.

    TODO antes do piloto: substituir por login real via QR + app iFood
    (task da Semana 1 do roadmap) — CPF digitado é o fallback do MVP.
    """
    if not is_valid_cpf_format(payload.cpf):
        raise HTTPException(status_code=400, detail="CPF inválido — precisa ter 11 dígitos.")

    table = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.restaurant_id == payload.restaurant_id,
            RestaurantTable.number == payload.table_number,
        )
        .first()
    )
    if not table:
        raise HTTPException(status_code=404, detail="Mesa não encontrada para este restaurante.")

    cpf_hash = hash_cpf(payload.cpf)
    customer = db.query(Customer).filter(Customer.cpf_hash == cpf_hash).first()
    is_new = customer is None
    if is_new:
        customer = Customer(cpf_hash=cpf_hash)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    return CustomerLookupResponse(
        customer_id=customer.id,
        name=customer.name,
        is_new=is_new,
        table_id=table.id,
    )
