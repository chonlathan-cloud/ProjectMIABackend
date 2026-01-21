from google.cloud import pubsub_v1
from src.config import settings
from typing import Dict, Any, AsyncGenerator, Callable
import json
import asyncio
from concurrent.futures import TimeoutError


class PubSubService:
    """Service for Google Cloud Pub/Sub operations."""
    
    def __init__(self):
        self.project_id = settings.google_cloud_project
        self.publisher = pubsub_v1.PublisherClient()
        self.subscriber = pubsub_v1.SubscriberClient()
        
        # Topic and subscription paths
        self.topic_path = self.publisher.topic_path(
            self.project_id,
            settings.pubsub_topic_incoming
        )
        self.subscription_path = self.subscriber.subscription_path(
            self.project_id,
            settings.pubsub_subscription_incoming
        )
    
    async def publish_message(self, message_data: Dict[str, Any]) -> str:
        """
        Publish a message to Pub/Sub topic.
        
        Args:
            message_data: Dictionary to publish as JSON
            
        Returns:
            Message ID
        """
        try:
            # Convert dict to JSON bytes
            message_bytes = json.dumps(message_data).encode("utf-8")
            
            # Publish message
            future = self.publisher.publish(self.topic_path, message_bytes)
            
            # Wait for publish to complete
            message_id = future.result()
            
            return message_id
            
        except Exception as e:
            raise Exception(f"Failed to publish message: {str(e)}")
    
    async def subscribe_filtered(
        self,
        shop_id: str,
        customer_id: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to Pub/Sub with filtering for specific shop and customer.
        
        Args:
            shop_id: Filter messages for this shop
            customer_id: Filter messages for this customer
            callback: Function to call when message received
        """
        def message_callback(message: pubsub_v1.subscriber.message.Message):
            try:
                # Parse message data
                data = json.loads(message.data.decode("utf-8"))
                
                # Filter by shop_id and customer_id
                if (data.get("shop_id") == shop_id and 
                    data.get("customer_id") == customer_id):
                    callback(data)
                
                # Acknowledge message
                message.ack()
                
            except Exception as e:
                print(f"Error processing message: {e}")
                message.nack()
        
        # Subscribe
        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=message_callback
        )
        
        try:
            # Keep subscription alive
            streaming_pull_future.result()
        except TimeoutError:
            streaming_pull_future.cancel()
            streaming_pull_future.result()
    
    async def stream_messages(
        self,
        shop_id: str,
        customer_id: str,
        timeout: int = 300  # 5 minutes default
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream messages as async generator for SSE.
        
        Args:
            shop_id: Filter messages for this shop
            customer_id: Filter messages for this customer
            timeout: Timeout in seconds
            
        Yields:
            Message data dictionaries
        """
        queue: asyncio.Queue = asyncio.Queue()
        
        def callback(data: Dict[str, Any]):
            # Put message in queue for async iteration
            asyncio.create_task(queue.put(data))
        
        # Start subscription in background
        subscription_task = asyncio.create_task(
            self.subscribe_filtered(shop_id, customer_id, callback)
        )
        
        try:
            # Stream messages from queue
            start_time = asyncio.get_event_loop().time()
            
            while True:
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    break
                
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield message
                    
                except asyncio.TimeoutError:
                    # No message received, continue waiting
                    continue
                    
        finally:
            # Cancel subscription
            subscription_task.cancel()
            try:
                await subscription_task
            except asyncio.CancelledError:
                pass


# Global Pub/Sub service instance
pubsub_service = PubSubService()
