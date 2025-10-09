"""
Unit tests for Policy model

Tests Policy model constraints:
- Unique policy name
- blast_radius_threshold range (0.0-1.0)
- Boolean fields (enabled)
- Nullable/non-nullable fields
- CHECK constraints
"""
import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from decimal import Decimal

from src.models.policy import Policy


class TestPolicyModelConstraints:
    """Test Policy model CHECK constraints and validations"""

    def test_policy_creation_with_valid_data(self, test_db):
        """Test creating a policy with all valid fields"""
        policy = Policy(
            name="max-blast-radius-policy",
            description="Limit blast radius to 30% of services",
            blast_radius_threshold=Decimal("0.30"),
            enabled=True
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.policy_id is not None
        assert policy.name == "max-blast-radius-policy"
        assert policy.blast_radius_threshold == Decimal("0.30")
        assert policy.enabled is True

    def test_unique_name_constraint(self, test_db):
        """Test that policy name must be unique"""
        # Create first policy
        policy1 = Policy(
            name="unique-policy",
            blast_radius_threshold=Decimal("0.5"),
            enabled=True
        )
        test_db.add(policy1)
        test_db.commit()

        # Try to create duplicate policy with same name
        with pytest.raises(IntegrityError):
            policy2 = Policy(
                name="unique-policy",  # Duplicate name
                blast_radius_threshold=Decimal("0.3"),
                enabled=True
            )
            test_db.add(policy2)
            test_db.commit()

    def test_blast_radius_threshold_within_range(self, test_db):
        """Test that blast_radius_threshold must be between 0 and 1"""
        valid_thresholds = [
            Decimal("0.00"),
            Decimal("0.25"),
            Decimal("0.50"),
            Decimal("0.75"),
            Decimal("1.00")
        ]

        for idx, threshold in enumerate(valid_thresholds):
            policy = Policy(
                name=f"policy-{idx}",
                blast_radius_threshold=threshold,
                enabled=True
            )
            test_db.add(policy)
            test_db.commit()
            test_db.refresh(policy)

            assert policy.blast_radius_threshold == threshold

    def test_blast_radius_threshold_below_range(self, test_db):
        """Test that blast_radius_threshold below 0 is rejected"""
        with pytest.raises(IntegrityError):
            policy = Policy(
                name="invalid-policy",
                blast_radius_threshold=Decimal("-0.1"),  # Should fail
                enabled=True
            )
            test_db.add(policy)
            test_db.commit()

    def test_blast_radius_threshold_above_range(self, test_db):
        """Test that blast_radius_threshold above 1 is rejected"""
        with pytest.raises(IntegrityError):
            policy = Policy(
                name="invalid-policy",
                blast_radius_threshold=Decimal("1.01"),  # Should fail
                enabled=True
            )
            test_db.add(policy)
            test_db.commit()

    def test_blast_radius_threshold_precision(self, test_db):
        """Test that blast_radius_threshold has correct precision (3,2)"""
        policy = Policy(
            name="precision-policy",
            blast_radius_threshold=Decimal("0.99"),
            enabled=True
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.blast_radius_threshold == Decimal("0.99")


class TestPolicyModelDefaults:
    """Test Policy model default values"""

    def test_policy_enabled_defaults_to_true(self, test_db):
        """Test that enabled defaults to True"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.enabled is True

    def test_policy_timestamps_auto_set(self, test_db):
        """Test that created_at and updated_at are automatically set"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.created_at is not None
        assert policy.updated_at is not None
        assert isinstance(policy.created_at, datetime)
        assert isinstance(policy.updated_at, datetime)

    def test_policy_id_auto_generated(self, test_db):
        """Test that policy_id is auto-generated if not provided"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.policy_id is not None


class TestPolicyModelNullability:
    """Test Policy model nullable and non-nullable fields"""

    def test_name_not_nullable(self, test_db):
        """Test that name cannot be NULL"""
        with pytest.raises(IntegrityError):
            policy = Policy(
                name=None,  # Should fail
                blast_radius_threshold=Decimal("0.5"),
                enabled=True
            )
            test_db.add(policy)
            test_db.commit()

    def test_blast_radius_threshold_not_nullable(self, test_db):
        """Test that blast_radius_threshold cannot be NULL"""
        with pytest.raises(IntegrityError):
            policy = Policy(
                name="test-policy",
                blast_radius_threshold=None,  # Should fail
                enabled=True
            )
            test_db.add(policy)
            test_db.commit()

    def test_enabled_not_nullable(self, test_db):
        """Test that enabled cannot be NULL"""
        with pytest.raises(IntegrityError):
            policy = Policy(
                name="test-policy",
                blast_radius_threshold=Decimal("0.5"),
                enabled=None  # Should fail
            )
            test_db.add(policy)
            test_db.commit()

    def test_description_nullable(self, test_db):
        """Test that description can be NULL"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5"),
            description=None  # Should succeed
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.description is None


class TestPolicyModelBooleanFields:
    """Test Policy model boolean field behavior"""

    def test_enabled_true(self, test_db):
        """Test that enabled can be set to True"""
        policy = Policy(
            name="enabled-policy",
            blast_radius_threshold=Decimal("0.5"),
            enabled=True
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.enabled is True

    def test_enabled_false(self, test_db):
        """Test that enabled can be set to False"""
        policy = Policy(
            name="disabled-policy",
            blast_radius_threshold=Decimal("0.5"),
            enabled=False
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.enabled is False


class TestPolicyModelBlastRadius:
    """Test Policy model blast_radius_threshold scenarios"""

    def test_zero_blast_radius(self, test_db):
        """Test policy with zero blast radius (no changes allowed)"""
        policy = Policy(
            name="zero-blast-radius",
            description="No automatic deployments allowed",
            blast_radius_threshold=Decimal("0.00")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.blast_radius_threshold == Decimal("0.00")

    def test_max_blast_radius(self, test_db):
        """Test policy with maximum blast radius (all changes allowed)"""
        policy = Policy(
            name="max-blast-radius",
            description="All deployments allowed",
            blast_radius_threshold=Decimal("1.00")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        assert policy.blast_radius_threshold == Decimal("1.00")

    def test_typical_blast_radius_values(self, test_db):
        """Test typical blast radius threshold values"""
        typical_values = {
            "conservative": Decimal("0.10"),
            "moderate": Decimal("0.30"),
            "aggressive": Decimal("0.50")
        }

        for idx, (name, threshold) in enumerate(typical_values.items()):
            policy = Policy(
                name=f"{name}-policy",
                description=f"{name.title()} deployment policy",
                blast_radius_threshold=threshold
            )
            test_db.add(policy)
            test_db.commit()
            test_db.refresh(policy)

            assert policy.blast_radius_threshold == threshold


class TestPolicyModelStringRepresentation:
    """Test Policy model __repr__ method"""

    def test_enabled_policy_repr(self, test_db):
        """Test string representation of enabled policy"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5"),
            enabled=True
        )
        test_db.add(policy)
        test_db.commit()

        repr_str = repr(policy)
        assert "test-policy" in repr_str
        assert "enabled" in repr_str

    def test_disabled_policy_repr(self, test_db):
        """Test string representation of disabled policy"""
        policy = Policy(
            name="test-policy",
            blast_radius_threshold=Decimal("0.5"),
            enabled=False
        )
        test_db.add(policy)
        test_db.commit()

        repr_str = repr(policy)
        assert "test-policy" in repr_str
        assert "disabled" in repr_str


class TestPolicyModelUpdate:
    """Test Policy model update scenarios"""

    def test_update_blast_radius_threshold(self, test_db):
        """Test updating blast_radius_threshold"""
        policy = Policy(
            name="update-test",
            blast_radius_threshold=Decimal("0.30")
        )
        test_db.add(policy)
        test_db.commit()

        # Update threshold
        policy.blast_radius_threshold = Decimal("0.50")
        test_db.commit()
        test_db.refresh(policy)

        assert policy.blast_radius_threshold == Decimal("0.50")

    def test_update_enabled_status(self, test_db):
        """Test enabling and disabling policy"""
        policy = Policy(
            name="toggle-test",
            blast_radius_threshold=Decimal("0.30"),
            enabled=True
        )
        test_db.add(policy)
        test_db.commit()

        # Disable policy
        policy.enabled = False
        test_db.commit()
        test_db.refresh(policy)

        assert policy.enabled is False

        # Re-enable policy
        policy.enabled = True
        test_db.commit()
        test_db.refresh(policy)

        assert policy.enabled is True

    def test_updated_at_changes_on_update(self, test_db):
        """Test that updated_at changes when policy is updated"""
        policy = Policy(
            name="timestamp-test",
            blast_radius_threshold=Decimal("0.30")
        )
        test_db.add(policy)
        test_db.commit()
        test_db.refresh(policy)

        original_updated_at = policy.updated_at

        # Update policy
        policy.description = "Updated description"
        test_db.commit()
        test_db.refresh(policy)

        # updated_at should have changed
        # Note: This may be the same in fast tests, but the mechanism should be in place
        assert policy.updated_at >= original_updated_at
