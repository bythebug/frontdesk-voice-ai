"""Customer lookup/creation tools."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_registry import registry
from app.db.repositories import CustomerRepository


class LookupCustomerInput(BaseModel):
    first_name: str
    last_name: str


class LookupCustomerOutput(BaseModel):
    found: bool
    customer_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None


@registry.register(
    "lookup_customer",
    "Look up an existing patient by first and last name to retrieve their customer_id.",
    LookupCustomerInput,
)
async def lookup_customer(session: AsyncSession, args: LookupCustomerInput) -> LookupCustomerOutput:
    customer = await CustomerRepository(session).find_by_name(args.first_name, args.last_name)
    if customer is None:
        return LookupCustomerOutput(found=False)
    return LookupCustomerOutput(
        found=True,
        customer_id=str(customer.id),
        first_name=customer.first_name,
        last_name=customer.last_name,
        phone=customer.phone,
        email=customer.email,
    )


class CreateCustomerInput(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    email: str | None = None


class CreateCustomerOutput(BaseModel):
    customer_id: str
    first_name: str
    last_name: str


@registry.register(
    "create_customer",
    "Create a new patient record. Only call this after lookup_customer found no match.",
    CreateCustomerInput,
)
async def create_customer(session: AsyncSession, args: CreateCustomerInput) -> CreateCustomerOutput:
    customer = await CustomerRepository(session).create(
        first_name=args.first_name, last_name=args.last_name, phone=args.phone, email=args.email
    )
    return CreateCustomerOutput(
        customer_id=str(customer.id), first_name=customer.first_name, last_name=customer.last_name
    )
