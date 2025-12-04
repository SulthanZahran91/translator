"""Glossaries API routes."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import DbSessionDep
from backend.api.routes.auth import CurrentUserDep
from backend.api.schemas.glossary import (
    BulkTermImport,
    GlossaryCreate,
    GlossaryListResponse,
    GlossaryResponse,
    GlossaryUpdate,
    TermCreate,
    TermListResponse,
    TermResponse,
    TermUpdate,
)
from backend.models.glossary import GlossaryTerm, UserGlossary

router = APIRouter(prefix="/glossaries", tags=["Glossaries"])


async def get_user_glossary(
    db: AsyncSession,
    glossary_id: str,
    user_id: str,
) -> UserGlossary:
    """Get a user's glossary or raise 404."""
    result = await db.execute(
        select(UserGlossary).where(
            UserGlossary.id == glossary_id,
            UserGlossary.user_id == user_id,
        )
    )
    glossary = result.scalar_one_or_none()

    if not glossary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Glossary not found",
        )

    return glossary


@router.post("", response_model=GlossaryResponse, status_code=status.HTTP_201_CREATED)
async def create_glossary(
    data: GlossaryCreate,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> UserGlossary:
    """Create a new glossary."""
    glossary = UserGlossary(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        domain=data.domain,
    )
    db.add(glossary)
    await db.flush()

    return glossary


@router.get("", response_model=GlossaryListResponse)
async def list_glossaries(
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> GlossaryListResponse:
    """List user's glossaries."""
    result = await db.execute(
        select(UserGlossary)
        .where(UserGlossary.user_id == current_user.id)
        .order_by(UserGlossary.name)
    )
    glossaries = list(result.scalars().all())

    # Get term counts
    responses = []
    for glossary in glossaries:
        count_result = await db.execute(
            select(func.count(GlossaryTerm.id))
            .where(GlossaryTerm.glossary_id == glossary.id)
        )
        term_count = count_result.scalar() or 0

        responses.append(GlossaryResponse(
            id=glossary.id,
            name=glossary.name,
            description=glossary.description,
            domain=glossary.domain,
            term_count=term_count,
            created_at=glossary.created_at,
            updated_at=glossary.updated_at,
        ))

    return GlossaryListResponse(
        glossaries=responses,
        total=len(responses),
    )


@router.get("/{glossary_id}", response_model=GlossaryResponse)
async def get_glossary(
    glossary_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> GlossaryResponse:
    """Get a specific glossary."""
    glossary = await get_user_glossary(db, glossary_id, current_user.id)

    count_result = await db.execute(
        select(func.count(GlossaryTerm.id))
        .where(GlossaryTerm.glossary_id == glossary.id)
    )
    term_count = count_result.scalar() or 0

    return GlossaryResponse(
        id=glossary.id,
        name=glossary.name,
        description=glossary.description,
        domain=glossary.domain,
        term_count=term_count,
        created_at=glossary.created_at,
        updated_at=glossary.updated_at,
    )


@router.patch("/{glossary_id}", response_model=GlossaryResponse)
async def update_glossary(
    glossary_id: str,
    data: GlossaryUpdate,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> GlossaryResponse:
    """Update a glossary."""
    glossary = await get_user_glossary(db, glossary_id, current_user.id)

    if data.name is not None:
        glossary.name = data.name
    if data.description is not None:
        glossary.description = data.description
    if data.domain is not None:
        glossary.domain = data.domain

    await db.flush()

    count_result = await db.execute(
        select(func.count(GlossaryTerm.id))
        .where(GlossaryTerm.glossary_id == glossary.id)
    )
    term_count = count_result.scalar() or 0

    return GlossaryResponse(
        id=glossary.id,
        name=glossary.name,
        description=glossary.description,
        domain=glossary.domain,
        term_count=term_count,
        created_at=glossary.created_at,
        updated_at=glossary.updated_at,
    )


@router.delete("/{glossary_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_glossary(
    glossary_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    """Delete a glossary."""
    glossary = await get_user_glossary(db, glossary_id, current_user.id)
    await db.delete(glossary)
    await db.flush()


# Term endpoints

@router.get("/{glossary_id}/terms", response_model=TermListResponse)
async def list_terms(
    glossary_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
    search: str | None = None,
) -> TermListResponse:
    """List terms in a glossary."""
    await get_user_glossary(db, glossary_id, current_user.id)

    query = select(GlossaryTerm).where(GlossaryTerm.glossary_id == glossary_id)

    if search:
        query = query.where(
            GlossaryTerm.source_term.ilike(f"%{search}%") |
            GlossaryTerm.target_term.ilike(f"%{search}%")
        )

    query = query.order_by(GlossaryTerm.source_term)

    result = await db.execute(query)
    terms = list(result.scalars().all())

    return TermListResponse(
        terms=[TermResponse.model_validate(t) for t in terms],
        total=len(terms),
    )


@router.post("/{glossary_id}/terms", response_model=TermResponse, status_code=status.HTTP_201_CREATED)
async def create_term(
    glossary_id: str,
    data: TermCreate,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> GlossaryTerm:
    """Add a term to a glossary."""
    await get_user_glossary(db, glossary_id, current_user.id)

    # Check for duplicate
    existing = await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.glossary_id == glossary_id,
            GlossaryTerm.source_term == data.source_term,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Term already exists in this glossary",
        )

    term = GlossaryTerm(
        glossary_id=glossary_id,
        source_term=data.source_term,
        target_term=data.target_term,
        context=data.context,
        domain=data.domain,
        definition=data.definition,
        source="user_provided",
        confidence="high",
    )
    db.add(term)
    await db.flush()

    return term


@router.patch("/{glossary_id}/terms/{term_id}", response_model=TermResponse)
async def update_term(
    glossary_id: str,
    term_id: str,
    data: TermUpdate,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> GlossaryTerm:
    """Update a term."""
    await get_user_glossary(db, glossary_id, current_user.id)

    result = await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.id == term_id,
            GlossaryTerm.glossary_id == glossary_id,
        )
    )
    term = result.scalar_one_or_none()

    if not term:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Term not found",
        )

    if data.target_term is not None:
        term.target_term = data.target_term
    if data.context is not None:
        term.context = data.context
    if data.domain is not None:
        term.domain = data.domain
    if data.definition is not None:
        term.definition = data.definition

    await db.flush()

    return term


@router.delete("/{glossary_id}/terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term(
    glossary_id: str,
    term_id: str,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    """Delete a term."""
    await get_user_glossary(db, glossary_id, current_user.id)

    result = await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.id == term_id,
            GlossaryTerm.glossary_id == glossary_id,
        )
    )
    term = result.scalar_one_or_none()

    if not term:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Term not found",
        )

    await db.delete(term)
    await db.flush()


@router.post("/{glossary_id}/import", response_model=TermListResponse)
async def import_terms(
    glossary_id: str,
    data: BulkTermImport,
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> TermListResponse:
    """Bulk import terms into a glossary."""
    await get_user_glossary(db, glossary_id, current_user.id)

    imported_terms: list[GlossaryTerm] = []

    for term_data in data.terms:
        # Skip duplicates
        existing = await db.execute(
            select(GlossaryTerm).where(
                GlossaryTerm.glossary_id == glossary_id,
                GlossaryTerm.source_term == term_data.source_term,
            )
        )
        if existing.scalar_one_or_none():
            continue

        term = GlossaryTerm(
            glossary_id=glossary_id,
            source_term=term_data.source_term,
            target_term=term_data.target_term,
            context=term_data.context,
            domain=term_data.domain,
            definition=term_data.definition,
            source="user_provided",
            confidence="high",
        )
        db.add(term)
        imported_terms.append(term)

    await db.flush()

    return TermListResponse(
        terms=[TermResponse.model_validate(t) for t in imported_terms],
        total=len(imported_terms),
    )

