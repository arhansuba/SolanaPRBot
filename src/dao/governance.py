from typing import List, Dict, Optional, Any
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
import asyncio
import aiohttp
from decimal import Decimal
import backoff

from blockchain.crossmint.wallet import WalletManager
from dao.token import TokenManager

logger = logging.getLogger(__name__)

class ProposalStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    DEFEATED = "defeated"
    EXECUTED = "executed"
    CANCELLED = "cancelled"

class VoteType(Enum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"

@dataclass
class Vote:
    voter: str
    proposal_id: int
    vote_type: VoteType
    voting_power: Decimal
    timestamp: datetime

@dataclass
class Proposal:
    id: int
    title: str
    description: str
    proposer: str
    start_time: datetime
    end_time: datetime
    execution_delay: timedelta
    status: ProposalStatus
    required_quorum: Decimal
    votes_for: Decimal = Decimal(0)
    votes_against: Decimal = Decimal(0)
    votes_abstain: Decimal = Decimal(0)
    execution_payload: Optional[Dict] = None
    executed_at: Optional[datetime] = None

class GovernanceConfig:
    def __init__(self):
        self.min_proposal_power = Decimal("100000")  # Min tokens to create proposal
        self.voting_delay = timedelta(hours=24)      # Delay before voting starts
        self.voting_period = timedelta(days=3)       # Voting duration
        self.execution_delay = timedelta(days=2)     # Timelock period
        self.required_quorum = Decimal("0.04")       # 4% quorum
        self.proposal_threshold = Decimal("0.5")     # 50% approval threshold

class GovernanceManager:
    def __init__(
        self,
        token_manager: TokenManager,
        wallet_manager: WalletManager,
        config: Optional[GovernanceConfig] = None
    ):
        self.token_manager = token_manager
        self.wallet_manager = wallet_manager
        self.config = config or GovernanceConfig()
        
        # In-memory storage (replace with database in production)
        self.proposals: Dict[int, Proposal] = {}
        self.votes: Dict[int, List[Vote]] = {}
        self.next_proposal_id: int = 1

    async def create_proposal(
        self,
        title: str,
        description: str,
        proposer: str,
        execution_payload: Optional[Dict] = None
    ) -> Proposal:
        """Create a new governance proposal."""
        try:
            # Check if proposer has enough tokens
            proposer_balance = await self.token_manager.get_balance(proposer)
            if proposer_balance < self.config.min_proposal_power:
                raise ValueError(
                    f"Insufficient tokens to create proposal. "
                    f"Required: {self.config.min_proposal_power}, "
                    f"Current: {proposer_balance}"
                )

            # Create proposal
            now = datetime.now()
            proposal = Proposal(
                id=self.next_proposal_id,
                title=title,
                description=description,
                proposer=proposer,
                start_time=now + self.config.voting_delay,
                end_time=now + self.config.voting_delay + self.config.voting_period,
                execution_delay=self.config.execution_delay,
                status=ProposalStatus.DRAFT,
                required_quorum=self.config.required_quorum,
                execution_payload=execution_payload
            )

            # Store proposal
            self.proposals[proposal.id] = proposal
            self.votes[proposal.id] = []
            self.next_proposal_id += 1

            logger.info(f"Created proposal {proposal.id}: {title}")
            return proposal

        except Exception as e:
            logger.error(f"Error creating proposal: {str(e)}")
            raise

    async def cast_vote(
        self,
        voter: str,
        proposal_id: int,
        vote_type: VoteType
    ) -> Vote:
        """Cast a vote on a proposal."""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal {proposal_id} not found")

            # Check if proposal is active
            now = datetime.now()
            if now < proposal.start_time:
                raise ValueError("Voting has not started yet")
            if now > proposal.end_time:
                raise ValueError("Voting has ended")

            # Get voter's voting power (tokens held at proposal creation)
            voting_power = await self.token_manager.get_balance(voter)
            
            # Check if already voted
            existing_votes = [v for v in self.votes[proposal_id] if v.voter == voter]
            if existing_votes:
                raise ValueError("Already voted on this proposal")

            # Create and record vote
            vote = Vote(
                voter=voter,
                proposal_id=proposal_id,
                vote_type=vote_type,
                voting_power=voting_power,
                timestamp=now
            )
            
            self.votes[proposal_id].append(vote)

            # Update proposal vote counts
            if vote_type == VoteType.FOR:
                proposal.votes_for += voting_power
            elif vote_type == VoteType.AGAINST:
                proposal.votes_against += voting_power
            else:
                proposal.votes_abstain += voting_power

            await self._check_proposal_state(proposal)
            
            logger.info(
                f"Recorded vote from {voter} on proposal {proposal_id}: {vote_type.value}"
            )
            return vote

        except Exception as e:
            logger.error(f"Error casting vote: {str(e)}")
            raise

    async def _check_proposal_state(self, proposal: Proposal):
        """Check and update proposal state."""
        now = datetime.now()
        
        if proposal.status == ProposalStatus.DRAFT and now >= proposal.start_time:
            proposal.status = ProposalStatus.ACTIVE
        
        elif proposal.status == ProposalStatus.ACTIVE and now >= proposal.end_time:
            total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
            total_supply = await self.token_manager.get_total_supply()
            
            # Check quorum
            if total_votes / total_supply >= proposal.required_quorum:
                # Check approval threshold
                if proposal.votes_for / (proposal.votes_for + proposal.votes_against) >= self.config.proposal_threshold:
                    proposal.status = ProposalStatus.SUCCEEDED
                else:
                    proposal.status = ProposalStatus.DEFEATED
            else:
                proposal.status = ProposalStatus.DEFEATED

    async def execute_proposal(self, proposal_id: int) -> bool:
        """Execute a successful proposal."""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal {proposal_id} not found")

            # Check if proposal can be executed
            if proposal.status != ProposalStatus.SUCCEEDED:
                raise ValueError("Proposal is not in succeeded state")

            now = datetime.now()
            execution_time = proposal.end_time + proposal.execution_delay
            if now < execution_time:
                raise ValueError("Execution delay has not passed")

            if proposal.execution_payload:
                # Execute the proposal's payload
                await self._execute_payload(proposal.execution_payload)

            proposal.status = ProposalStatus.EXECUTED
            proposal.executed_at = now
            
            logger.info(f"Executed proposal {proposal_id}")
            return True

        except Exception as e:
            logger.error(f"Error executing proposal: {str(e)}")
            raise

    async def _execute_payload(self, payload: Dict):
        """Execute a proposal's payload."""
        # This would contain the logic to execute different types of proposals
        action_type = payload.get('type')
        
        if action_type == 'transfer':
            await self.token_manager.transfer(
                payload['from_address'],
                payload['to_address'],
                Decimal(payload['amount'])
            )
        elif action_type == 'parameter_change':
            # Update governance parameters
            parameter = payload['parameter']
            value = payload['value']
            setattr(self.config, parameter, value)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def get_proposal(self, proposal_id: int) -> Optional[Proposal]:
        """Get proposal details."""
        proposal = self.proposals.get(proposal_id)
        if proposal:
            await self._check_proposal_state(proposal)
        return proposal

    async def get_votes(self, proposal_id: int) -> List[Vote]:
        """Get all votes for a proposal."""
        return self.votes.get(proposal_id, [])

    async def get_voter_power(self, voter: str) -> Decimal:
        """Get voter's current voting power."""
        return await self.token_manager.get_balance(voter)

    async def get_proposal_result(self, proposal_id: int) -> Dict[str, Any]:
        """Get detailed results of a proposal."""
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        total_votes = proposal.votes_for + proposal.votes_against + proposal.votes_abstain
        total_supply = await self.token_manager.get_total_supply()

        return {
            'status': proposal.status.value,
            'votes_for': float(proposal.votes_for),
            'votes_against': float(proposal.votes_against),
            'votes_abstain': float(proposal.votes_abstain),
            'participation_rate': float(total_votes / total_supply),
            'approval_rate': float(proposal.votes_for / (proposal.votes_for + proposal.votes_against)) if proposal.votes_for + proposal.votes_against > 0 else 0,
            'quorum_reached': (total_votes / total_supply) >= proposal.required_quorum
        }

# Example usage
if __name__ == "__main__":
    async def main():
        # Initialize managers (mock objects for example)
        governance = GovernanceManager(
            token_manager=None,  # Add TokenManager instance
            wallet_manager=None  # Add WalletManager instance
        )
        
        try:
            # Create proposal
            proposal = await governance.create_proposal(
                title="Update Protocol Fee",
                description="Proposal to update protocol fee from 0.3% to 0.2%",
                proposer="proposer_address",
                execution_payload={
                    'type': 'parameter_change',
                    'parameter': 'protocol_fee',
                    'value': 0.002
                }
            )
            
            # Cast votes
            await governance.cast_vote(
                voter="voter1_address",
                proposal_id=proposal.id,
                vote_type=VoteType.FOR
            )
            
            # Get results
            results = await governance.get_proposal_result(proposal.id)
            print(f"Proposal results: {json.dumps(results, indent=2)}")
            
        except Exception as e:
            print(f"Error: {str(e)}")

    asyncio.run(main())