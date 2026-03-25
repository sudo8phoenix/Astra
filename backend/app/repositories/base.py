"""Base repository implementing common CRUD patterns."""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Generic type for model
T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """Abstract base repository with common CRUD operations.
    
    Provides standard database operations for all entity repositories.
    """

    def __init__(self, session: Session, model_class: type):
        """Initialize repository with session and model class.
        
        Args:
            session: SQLAlchemy session
            model_class: Model class this repository manages
        """
        self.session = session
        self.model_class = model_class

    def create(self, **kwargs) -> T:
        """Create a new entity.
        
        Args:
            **kwargs: Entity attributes
            
        Returns:
            Created entity instance
            
        Raises:
            SQLAlchemyError: If creation fails
        """
        try:
            entity = self.model_class(**kwargs)
            self.session.add(entity)
            self.session.flush()
            logger.info(f"Created {self.model_class.__name__}: {entity.id}")
            return entity
        except SQLAlchemyError as e:
            logger.error(f"Error creating {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by ID.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            Entity instance or None if not found
        """
        try:
            return self.session.query(self.model_class).filter(
                self.model_class.id == entity_id
            ).first()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving {self.model_class.__name__}: {e}")
            return None

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all entities with pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            
        Returns:
            List of entity instances
        """
        try:
            return self.session.query(self.model_class).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving all {self.model_class.__name__}: {e}")
            return []

    def update(self, entity_id: str, **kwargs) -> Optional[T]:
        """Update an entity.
        
        Args:
            entity_id: Entity ID
            **kwargs: Attributes to update
            
        Returns:
            Updated entity instance or None if not found
            
        Raises:
            SQLAlchemyError: If update fails
        """
        try:
            entity = self.get_by_id(entity_id)
            if not entity:
                logger.warning(f"{self.model_class.__name__} not found: {entity_id}")
                return None
            
            # Update attributes, excluding id and created_at
            for key, value in kwargs.items():
                if key not in ['id', 'created_at'] and hasattr(entity, key):
                    setattr(entity, key, value)
            
            self.session.flush()
            logger.info(f"Updated {self.model_class.__name__}: {entity_id}")
            return entity
        except SQLAlchemyError as e:
            logger.error(f"Error updating {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def delete(self, entity_id: str) -> bool:
        """Delete an entity.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            SQLAlchemyError: If deletion fails
        """
        try:
            entity = self.get_by_id(entity_id)
            if not entity:
                logger.warning(f"{self.model_class.__name__} not found for deletion: {entity_id}")
                return False
            
            self.session.delete(entity)
            self.session.flush()
            logger.info(f"Deleted {self.model_class.__name__}: {entity_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def exists(self, entity_id: str) -> bool:
        """Check if entity exists.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            True if exists, False otherwise
        """
        try:
            return self.session.query(self.model_class).filter(
                self.model_class.id == entity_id
            ).first() is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking existence of {self.model_class.__name__}: {e}")
            return False

    def count(self, **filters) -> int:
        """Count entities matching filters.
        
        Args:
            **filters: Filter conditions
            
        Returns:
            Count of matching entities
        """
        try:
            query = self.session.query(self.model_class)
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model_class.__name__}: {e}")
            return 0

    def find(self, **filters) -> List[T]:
        """Find entities by filters.
        
        Args:
            **filters: Filter conditions (AND logic)
            
        Returns:
            List of matching entities
        """
        try:
            query = self.session.query(self.model_class)
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error finding {self.model_class.__name__}: {e}")
            return []

    def find_one(self, **filters) -> Optional[T]:
        """Find first entity matching filters.
        
        Args:
            **filters: Filter conditions
            
        Returns:
            First matching entity or None
        """
        try:
            query = self.session.query(self.model_class)
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            return query.first()
        except SQLAlchemyError as e:
            logger.error(f"Error finding one {self.model_class.__name__}: {e}")
            return None

    def batch_create(self, entities_data: List[Dict[str, Any]]) -> List[T]:
        """Create multiple entities in batch.
        
        Args:
            entities_data: List of entity attribute dictionaries
            
        Returns:
            List of created entities
            
        Raises:
            SQLAlchemyError: If batch creation fails
        """
        try:
            entities = []
            for entity_data in entities_data:
                entity = self.model_class(**entity_data)
                entities.append(entity)
                self.session.add(entity)
            self.session.flush()
            logger.info(f"Batch created {len(entities)} {self.model_class.__name__} entities")
            return entities
        except SQLAlchemyError as e:
            logger.error(f"Error batch creating {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def batch_update(self, updates: List[Dict[str, Any]]) -> int:
        """Update multiple entities.
        
        Each update dict must have 'id' key.
        
        Args:
            updates: List of update dicts with 'id' key
            
        Returns:
            Number of entities updated
        """
        try:
            count = 0
            for update_data in updates:
                entity_id = update_data.pop('id')
                if self.update(entity_id, **update_data):
                    count += 1
            self.session.flush()
            logger.info(f"Batch updated {count} {self.model_class.__name__} entities")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Error batch updating {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def save(self, entity: T) -> T:
        """Save (insert or update) an entity.
        
        Args:
            entity: Entity instance
            
        Returns:
            Saved entity
        """
        try:
            self.session.merge(entity)
            self.session.flush()
            logger.info(f"Saved {self.model_class.__name__}: {entity.id}")
            return entity
        except SQLAlchemyError as e:
            logger.error(f"Error saving {self.model_class.__name__}: {e}")
            self.session.rollback()
            raise

    def commit(self) -> None:
        """Commit all pending changes."""
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error committing transaction: {e}")
            self.session.rollback()
            raise

    def rollback(self) -> None:
        """Rollback all pending changes."""
        self.session.rollback()
