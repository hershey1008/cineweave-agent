"""Only create the four additive CineWeave tables in an existing database."""
from app.database import engine
from app.models import ChatSession, ChatTurn, RecommendationEvent, RecommendationFeedback

if __name__ == "__main__":
    for model in [ChatSession, ChatTurn, RecommendationEvent, RecommendationFeedback]:
        model.__table__.create(engine, checkfirst=True)
    print("CineWeave additive schema is ready; existing tables were preserved.")
