from sqlalchemy import create_engine, Column, String, Integer, BigInteger, Text, ForeignKey, Date, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, DateTime
from datetime import datetime

Base = declarative_base()

class Channel(Base):
    __tablename__ = 'channels'

    channel_id = Column(String(50), primary_key=True)
    channel_name = Column(String(255), nullable=False)
    subscribers = Column(BigInteger)
    views = Column(BigInteger)
    total_videos = Column(BigInteger)
    playlist_id = Column(String(50))
    published_at = Column(String(50)) # Keeping as string for simplicity, can be DateTime
    thumbnail_url = Column(String(255))
    description = Column(Text)
    
    # Relationship
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")

class Video(Base):
    __tablename__ = 'videos'

    video_id = Column(String(50), primary_key=True)
    channel_id = Column(String(50), ForeignKey('channels.channel_id'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    published_at = Column(String(50))
    duration = Column(String(20))
    thumbnail_url = Column(String(255))
    
    # Relationship
    channel = relationship("Channel", back_populates="videos")
    # Relationship: A video has many statistics (one per fetch)
    stats = relationship("VideoStats", back_populates="video", cascade="all, delete-orphan")
    
    # Allow us to access comments for a video
    comments = relationship("Comment", back_populates="video", cascade="all, delete-orphan")

class VideoStats(Base):
    """
    Stores snapshots of video metrics over time.
    """
    __tablename__ = 'video_statistics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(50), ForeignKey('videos.video_id'), nullable=False, index=True)
    view_count = Column(BigInteger)
    like_count = Column(BigInteger)
    comment_count = Column(BigInteger)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationship: Stats belong to a video
    video = relationship("Video", back_populates="stats")

class Comment(Base):
    __tablename__ = 'comments'
    
    comment_id = Column(String(100), primary_key=True)
    video_id = Column(String(50), ForeignKey('videos.video_id'), nullable=False)
    author = Column(String(255))
    text = Column(Text)
    published_at = Column(DateTime)
    
    # Relationship
    video = relationship("Video", back_populates="comments")
