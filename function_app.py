# function_app.py

import logging
import json
import os
import azure.functions as func
#import redis
from redis_client import redis_client


# 중요: func.FunctionApp() 인스턴스는 프로젝트 전체에서 단 한 번만 정의되어야 합니다.
app = func.FunctionApp()

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. RobotStatusChangeLogger 함수 (Event Grid Trigger)
# 모든 로봇 상태 변경 이벤트를 수신하여 로그를 기록합니다.
# 로봇 상태 변경 이벤트를 수신하여 Cosmos DB에 실시간으로 업데이트합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
@app.cosmos_db_output(arg_name="outputDocument", 
                      database_name="RobotMonitoringDB", # 이름 수정 RobotMonitoringDB
                      container_name="LatestRobotStates", # 이름 수정 LatestRobotStates
                      connection="CosmosDBConnection", # 이름 수정
                      create_if_not_exists=False, # 컨테이너가 없으면 생성
                      partition_key="/deviceId" # 파티션 키 설정
                     )
@app.cosmos_db_output(arg_name="historyDocument", 
                      database_name="RobotMonitoringDB",
                      container_name="RobotStateHistory",
                      connection="CosmosDBConnection",
                      create_if_not_exists=True
                     )

def RobotStatusChangeLogger(event: func.EventGridEvent, 
                      outputDocument: func.Out[func.Document],
                      historyDocument: func.Out[func.Document]):
    logger.info('Python Event Grid trigger processed RobotStateUpdater event.')

    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Updater: Event body is empty or malformed: {event_data}")
            return

        # 1. '최종 상태'를 저장할 문서
        # 이 문서는 기존과 동일하게 deviceId를 id로 사용하여 upsert(덮어쓰기) 됩니다.
        robot_document_latest = {
            "id": robot_telemetry_body.get('deviceId'), # deviceId를 id로 사용하여 덮어쓰기
            "deviceId": robot_telemetry_body.get('deviceId'),
            "timestamp": robot_telemetry_body.get('ttimestamp'),
            "batteryLevel": robot_telemetry_body.get('batteryLevel'),
            "currentStatus": robot_telemetry_body.get('currentStatus'),
            "purificationStatus": robot_telemetry_body.get('purificationStatus'),
            "location": robot_telemetry_body.get('location'),
            "eventGridEventId": event.id
        }
        
        # 2. '이력 데이터'를 저장할 문서
        # uuid.uuid4()를 사용하여 매번 고유한 id를 생성합니다.
        # 이렇게 하면 새로운 문서가 생성되어 누적됩니다.
        robot_document_history = {
            "id": str(uuid.uuid4()), # 매번 새로운 고유 ID 생성
            "deviceId": robot_telemetry_body.get('deviceId'),
            "timestamp": robot_telemetry_body.get('ttimestamp'),
            "batteryLevel": robot_telemetry_body.get('batteryLevel'),
            "currentStatus": robot_telemetry_body.get('currentStatus'),
            "purificationStatus": robot_telemetry_body.get('purificationStatus'),
            "location": robot_telemetry_body.get('location'),
            "eventGridEventId": event.id
        }

        # 두 개의 출력 바인딩에 각각 다른 문서를 설정
        outputDocument.set(func.Document.from_json(json.dumps(robot_document_latest)))
        historyDocument.set(func.Document.from_json(json.dumps(robot_document_history)))
        
        logger.info(f"Updater: Updated latest status for DeviceId: {robot_document_latest['deviceId']}")
        logger.info(f"Updater: Logged historical data for DeviceId: {robot_document_history['deviceId']} with new id: {robot_document_history['id']}")

    except json.JSONDecodeError:
        logger.error(f"Updater: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Updater: Error processing Event Grid event: {e}", exc_info=True)



# ==============================================================================
# 2. MaintenanceScheduler 함수 (Event Grid Trigger)
# 특정 조건(배터리, 상태)을 만족하는 이벤트에 대해 알림을 보냅니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def MaintenanceScheduler(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed MaintenanceScheduler event.')
    
    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Scheduler: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')
        
        alert_triggered = False
        alert_reason = []

        if battery_level is not None and battery_level < 20:
            alert_triggered = True
            alert_reason.append(f"배터리 잔량 {battery_level}% 미만")

        if current_status.lower() == 'error':
            alert_triggered = True
            alert_reason.append(f"현재 상태 '{current_status}' (에러)")

        if alert_triggered:
            alert_subject = f"[긴급 알림] 로봇 {device_id} - 유지보수 필요!"
            alert_content = (
                f"로봇 ID: {device_id} (시간: {ttimestamp})\n"
                f"이유: {', '.join(alert_reason)}\n"
                f"현재 배터리: {battery_level}%, 상태: {current_status}\n\n"
                "자세한 내용은 호수 수질 관리 시스템을 확인해주세요."
            )
            
            logger.critical(f"Scheduler: Alert triggered for robot {device_id}: {alert_content}")
        else:
            logger.info(f"Scheduler: No alert triggered for robot {device_id} (Battery: {battery_level}%, Status: {current_status})")

    except json.JSONDecodeError:
        logger.error(f"Scheduler: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Scheduler: Error processing Event Grid event: {e}", exc_info=True)


# ==============================================================================
# 3. RealtimeStatePusher 함수 (Event Grid Trigger)
# 로봇 상태 변경 이벤트를 수신하여 Redis에만 최신 상태를 저장합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def RealtimeStatePusher(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed RealtimeStatePusher event.')

    if not redis_client:
        logger.error("Redis client is not initialized. Cannot process event.")
        return

    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Pusher: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId')
        if not device_id:
            logger.warning("Pusher: No deviceId found in event body. Cannot process.")
            return

        # Redis에 최신 상태 저장
        robot_data_json = json.dumps(robot_telemetry_body)
        redis_client.set(f"robot_status:{device_id}", robot_data_json)
        logger.info(f"Pusher: Updated Redis for DeviceId: {device_id}")

    except json.JSONDecodeError:
        logger.error(f"Pusher: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Pusher: Error processing Event Grid event: {e}", exc_info=True)


# 클라이언트가 초기 데이터를 로드하고 Polling할 API
# 이 함수는 Redis에서 모든 로봇의 최신 상태를 읽어와 반환합니다.
@app.route(route="latest-robots", auth_level=func.AuthLevel.FUNCTION)
def GetLatestRobots(req: func.HttpRequest) -> func.HttpResponse:
    logger.info('Python HTTP trigger function processed GetLatestRobots request.')
    
    if not redis_client:
        return func.HttpResponse("Redis is not available.", status_code=500)

    try:
        keys = redis_client.keys("robot_status:*")
        latest_states = []
        for key in keys:
            data = redis_client.get(key)
            if data:
                latest_states.append(json.loads(data))
        
        return func.HttpResponse(
            body=json.dumps(latest_states),
            mimetype="application/json"
        )

    except Exception as e:
        logger.error(f"Error reading from Redis: {e}", exc_info=True)
        return func.HttpResponse(
            "An error occurred while fetching data.",
            status_code=500
        )
