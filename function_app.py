# function_app.py

import logging
import json
import os
import azure.functions as func
import uuid  # UUID를 사용하기 위해 uuid 라이브러리 추가

#import sendgrid
#from sendgrid.helpers.mail import Email, Mail, Personalization

logger = logging.getLogger(__name__)

# 중요: func.FunctionApp() 인스턴스는 프로젝트 전체에서 단 한 번만 정의되어야 합니다.
app = func.FunctionApp()

# 환경 변수에서 데이터베이스 및 컨테이너 이름을 로드합니다.
# COSMOS_DB_DATABASE = os.getenv("CosmosDBDatabase", "RobotMonitoringDB")
# COSMOS_DB_CONTAINER = os.getenv("CosmosDBContainer", "LatestRobotStates")
# COSMOS_DB_CONNECTION_STRING = os.getenv("CosmosDBConnection", "")

# ==============================================================================
# 1. RobotStatusChangeLogger 함수 (Event Grid Trigger)
# 모든 로봇 상태 변경 이벤트를 수신하여 로그를 기록합니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def RobotStatusChangeLogger(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed RobotStatusChangeLogger event.')
    
    try:
        # NOTE: event.get_json()은 IoT Hub 이벤트의 'data' 필드 안의 내용을 반환합니다.
        event_data = event.get_json()
        
        # 'data' 필드가 없는 구조이므로 바로 'body'를 가져옵니다.
        # 이전 코드: event_data.get('data', {}).get('body', {})
        robot_telemetry_body = event_data.get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Logger: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel', 'N/A')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')

        log_message = (
            f"RobotTelemetryLog - DeviceId: {device_id}, "
            f"Timestamp: {ttimestamp}, "
            f"Battery: {battery_level}%, Status: {current_status}"
        )
        logger.info(log_message)

    except json.JSONDecodeError:
        logger.error(f"Logger: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Logger: Error processing Event Grid event: {e}", exc_info=True)


# ==============================================================================
# 2. MaintenanceScheduler 함수 (Event Grid Trigger)
# 특정 조건(배터리, 상태)을 만족하는 이벤트에 대해 알림을 보냅니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def MaintenanceScheduler(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed MaintenanceScheduler event.')
    
    try:
        event_data = event.get_json()
        # 'data' 필드가 없는 구조이므로 바로 'body'를 가져옵니다.
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

            # try:
            #     sg = sendgrid.SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            #     mail = Mail()
            #     mail.from_email = Email(os.environ.get('SENDER_EMAIL', 'sender@example.com'))
                
            #     personalization = Personalization()
            #     personalization.add_to(Email(os.environ.get('RECIPIENT_EMAIL', 'recipient@example.com')))
            #     mail.add_personalization(personalization)
                
            #     mail.subject = alert_subject
            #     mail.add_content("text/plain", alert_content)
                
            #     response = sg.send(mail)
            #     logger.info(f"Scheduler: Email sent. Status Code: {response.status_code}")
            # except Exception as e:
            #     logger.error(f"Scheduler: Error sending email via SendGrid: {e}")
        else:
            logger.info(f"Scheduler: No alert triggered for robot {device_id} (Battery: {battery_level}%, Status: {current_status})")

    except json.JSONDecodeError:
        logger.error(f"Scheduler: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Scheduler: Error processing Event Grid event: {e}", exc_info=True)


# ==============================================================================
# 3. RobotStateUpdater 함수 (Event Grid Trigger + Cosmos DB Output Binding)
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
def RobotStateUpdater(event: func.EventGridEvent, 
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









